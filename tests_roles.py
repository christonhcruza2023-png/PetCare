"""Role-based permission tests: admin vs viewer, and user management."""
import glob
import os
import re
import sys

import pymongo
import requests

BASE = "http://127.0.0.1:5000"

failures = []


def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        failures.append(name)


def csrf(sess, path):
    r = sess.get(BASE + path, timeout=10)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    if not m:
        print(f"NO CSRF on {path} (status {r.status_code})")
        sys.exit(1)
    return r, m.group(1)


def new_session():
    return requests.Session()


def register(sess, username, password, email=""):
    """Register (or log in if the account already exists). Returns status."""
    r = sess.get(BASE + "/register", timeout=10)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
    r = sess.post(BASE + "/register", data={
        "csrf_token": tok, "username": username, "email": email,
        "password": password, "confirm": password},
        allow_redirects=False, timeout=10)
    if r.status_code == 302:
        return r.status_code
    r = sess.get(BASE + "/login", timeout=10)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
    r = sess.post(BASE + "/login", data={"csrf_token": tok, "username": username,
                 "password": password}, allow_redirects=False, timeout=10)
    return r.status_code


# =========================================================================
# Reset
# =========================================================================
db = pymongo.MongoClient("mongodb://localhost:27017")["petcare_db"]
for c in ("pets", "settings", "activity", "users"):
    db[c].delete_many({})
for f in glob.glob("static/uploads/*.png"):
    os.remove(f)

# =========================================================================
# 1. FIRST ACCOUNT BECOMES ADMIN
# =========================================================================
print("--- Bootstrap: first account is admin ---")

admin_sess = new_session()
st = register(admin_sess, "boss_admin", "BossPass!1", "boss@example.com")
check("first account registers", st == 302, st)

boss = db["users"].find_one({"username": "boss_admin"})
check("first account stored", boss is not None)
check("first account role = admin", boss and boss.get("role") == "admin",
      boss.get("role") if boss else None)

# Second account must be a viewer
viewer_sess = new_session()
st = register(viewer_sess, "nice_viewer", "ViewerPass!2", "viewer@example.com")
check("second account registers", st == 302, st)

viewer = db["users"].find_one({"username": "nice_viewer"})
check("second account role = viewer", viewer and viewer.get("role") == "viewer",
      viewer.get("role") if viewer else None)

# =========================================================================
# 2. VIEWER IS READ-ONLY
# =========================================================================
print("--- Viewer is read-only ---")

# Read access works
for path in ("/", "/pets", "/settings"):
    r = viewer_sess.get(BASE + path, allow_redirects=False, timeout=10)
    check(f"viewer can GET {path}", r.status_code == 200, r.status_code)

# The dashboard must not show an "Add New Pet" button to a viewer
r = viewer_sess.get(BASE + "/", timeout=10)
check("viewer sees no Add New Pet button",
      'href="/pets/new"' not in r.text and "Add New Pet" not in r.text)

# Write routes -> 403 (not a redirect to login, they ARE signed in)
for path in ("/pets/new", "/pets/PET-0001/edit"):
    r = viewer_sess.get(BASE + path, allow_redirects=False, timeout=10)
    check(f"viewer GET {path} -> 403", r.status_code == 403, r.status_code)
    check(f"  ...and the 403 page explains it", "Access denied" in r.text)

# Write POSTs -> 403 and must not mutate anything
_, tok = csrf(viewer_sess, "/pets")
before = db["pets"].count_documents({})
r = viewer_sess.post(BASE + "/pets/create", allow_redirects=False, timeout=10,
                     data={"csrf_token": tok, "pet_name": "Sneaky",
                           "animal_type": "Dog", "owner_name": "X"})
check("viewer POST /pets/create -> 403", r.status_code == 403, r.status_code)
check("viewer create wrote nothing",
      db["pets"].count_documents({}) == before,
      f"{before} -> {db['pets'].count_documents({})}")

# Viewer cannot reach user management
r = viewer_sess.get(BASE + "/users", allow_redirects=False, timeout=10)
check("viewer GET /users -> 403", r.status_code == 403, r.status_code)

# Viewer must not see Edit/Delete buttons on records
r = viewer_sess.get(BASE + "/pets", timeout=10)
check("viewer sees no Edit button", ">Edit</a>" not in r.text)
check("viewer sees no Delete button", "js-delete-btn" not in r.text)

# =========================================================================
# 3. ADMIN CAN DO EVERYTHING
# =========================================================================
print("--- Admin can manage records ---")

r = admin_sess.get(BASE + "/pets/new", allow_redirects=False, timeout=10)
check("admin GET /pets/new -> 200", r.status_code == 200, r.status_code)

_, tok = csrf(admin_sess, "/pets/new")
r = admin_sess.post(BASE + "/pets/create", allow_redirects=False, timeout=10,
                    data={"csrf_token": tok, "pet_name": "AdminPet",
                          "animal_type": "Dog", "owner_name": "Boss"})
check("admin create -> 302", r.status_code == 302, r.status_code)
check("admin create wrote a record", db["pets"].count_documents({}) == 1)
pet_id = r.headers["Location"].rstrip("/").split("/")[-1] if r.status_code == 302 else None

r = admin_sess.get(BASE + "/pets", timeout=10)
check("admin sees Edit buttons", ">Edit</a>" in r.text)
check("admin sees Delete buttons", "js-delete-btn" in r.text)

if pet_id:
    _, tok = csrf(admin_sess, f"/pets/{pet_id}/edit")
    r = admin_sess.post(BASE + f"/pets/{pet_id}/update", allow_redirects=False,
                        timeout=10, data={"csrf_token": tok,
                                          "pet_name": "AdminPet2",
                                          "animal_type": "Dog",
                                          "owner_name": "Boss"})
    check("admin update -> 302", r.status_code == 302, r.status_code)
    check("admin update persisted",
          db["pets"].find_one({"pet_id": pet_id}, {"pet_name": 1})["pet_name"]
          == "AdminPet2")

# =========================================================================
# 4. ADMIN USER MANAGEMENT
# =========================================================================
print("--- Admin manages users ---")

r = admin_sess.get(BASE + "/users", allow_redirects=False, timeout=10)
check("admin GET /users -> 200", r.status_code == 200, r.status_code)
check("users page lists both accounts",
      "boss_admin" in r.text and "nice_viewer" in r.text)

# Promote the viewer to admin
_, tok = csrf(admin_sess, "/users")
r = admin_sess.post(BASE + f"/users/{viewer['_id']}/role", allow_redirects=False,
                    timeout=10, data={"csrf_token": tok, "role": "admin"})
check("promote viewer -> 302", r.status_code == 302, r.status_code)
check("viewer is now admin",
      db["users"].find_one({"_id": viewer["_id"]}, {"role": 1})["role"] == "admin")

# A freshly promoted admin can now write
r = viewer_sess.get(BASE + "/pets/new", allow_redirects=False, timeout=10)
check("promoted admin can open write route", r.status_code == 200, r.status_code)

# Demote back to viewer
_, tok = csrf(admin_sess, "/users")
r = admin_sess.post(BASE + f"/users/{viewer['_id']}/role", allow_redirects=False,
                    timeout=10, data={"csrf_token": tok, "role": "viewer"})
check("demote admin -> 302", r.status_code == 302, r.status_code)
check("user is viewer again",
      db["users"].find_one({"_id": viewer["_id"]}, {"role": 1})["role"] == "viewer")

# Demoted user immediately loses write access
r = viewer_sess.get(BASE + "/pets/new", allow_redirects=False, timeout=10)
check("demoted user loses write access", r.status_code == 403, r.status_code)

# Invalid role rejected
_, tok = csrf(admin_sess, "/users")
r = admin_sess.post(BASE + f"/users/{viewer['_id']}/role", allow_redirects=False,
                    timeout=10, data={"csrf_token": tok, "role": "superuser"})
check("invalid role rejected", r.status_code == 302 and
      db["users"].find_one({"_id": viewer["_id"]}, {"role": 1})["role"] == "viewer")

# =========================================================================
# 5. LOCK-OUT PROTECTION
# =========================================================================
print("--- Lock-out protection ---")

# Admin cannot delete their own account
_, tok = csrf(admin_sess, "/users")
r = admin_sess.post(BASE + f"/users/{boss['_id']}/delete", allow_redirects=False,
                    timeout=10, data={"csrf_token": tok})
check("admin cannot delete self", r.status_code == 302)
check("self-delete refused (still exists)",
      db["users"].find_one({"_id": boss["_id"]}) is not None)

# The last admin cannot be demoted
_, tok = csrf(admin_sess, "/users")
r = admin_sess.post(BASE + f"/users/{boss['_id']}/role", allow_redirects=False,
                    timeout=10, data={"csrf_token": tok, "role": "viewer"})
check("last admin cannot demote self", r.status_code == 302)
check("last admin still admin",
      db["users"].find_one({"_id": boss["_id"]}, {"role": 1})["role"] == "admin")

# Nonexistent user id -> friendly flash, no crash
_, tok = csrf(admin_sess, "/users")
r = admin_sess.post(BASE + "/users/000000000000000000000000/delete",
                    allow_redirects=False, timeout=10,
                    data={"csrf_token": tok})
check("deleting unknown user -> 302, no crash", r.status_code == 302, r.status_code)

# Garbage id -> no crash
r = admin_sess.get(BASE + "/users/not-an-objectid/edit", allow_redirects=False,
                   timeout=10)
check("garbage id route -> 404", r.status_code == 404, r.status_code)

# =========================================================================
# 6. ADMIN CAN DELETE A VIEWER, THEN WRITE ACCESS IS CLEAN
# =========================================================================
print("--- Admin deletes a viewer ---")

tmp = new_session()
st = register(tmp, "temp_user", "TempPass!3")
check("temp account registers", st == 302, st)
tmp_user = db["users"].find_one({"username": "temp_user"})
check("temp account is a viewer", tmp_user["role"] == "viewer")

_, tok = csrf(admin_sess, "/users")
r = admin_sess.post(BASE + f"/users/{tmp_user['_id']}/delete",
                    allow_redirects=False, timeout=10, data={"csrf_token": tok})
check("admin deletes viewer -> 302", r.status_code == 302, r.status_code)
check("viewer removed from Mongo",
      db["users"].find_one({"_id": tmp_user["_id"]}) is None)

# The deleted user's session must stop working for writes
r = tmp.get(BASE + "/pets/new", allow_redirects=False, timeout=10)
check("deleted user's session rejected", r.status_code in (302, 403),
      r.status_code)

# =========================================================================
# 7. ANONYMOUS BEHAVIOUR UNCHANGED
# =========================================================================
print("--- Anonymous visitors ---")

anon = new_session()
r = anon.get(BASE + "/pets/new", allow_redirects=False, timeout=10)
check("anon write route -> redirect to login",
      r.status_code == 302 and "/login" in r.headers.get("Location", ""),
      f"{r.status_code} {r.headers.get('Location', '')}")
r = anon.get(BASE + "/users", allow_redirects=False, timeout=10)
check("anon /users -> redirect to login",
      r.status_code == 302 and "/login" in r.headers.get("Location", ""),
      f"{r.status_code} {r.headers.get('Location', '')}")
r = anon.get(BASE + "/", allow_redirects=False, timeout=10)
check("anon can still read dashboard", r.status_code == 200, r.status_code)
check("anon sees Sign In", 'href="/login"' in r.text)
# For a visitor, "Add New Pet" is a legitimate onboarding path: following it
# must land on the sign-in page rather than a 403.
check("anon Add New Pet is offered", re.search(r'href="/pets/new"', r.text) is not None)
r = anon.get(BASE + "/pets/new", allow_redirects=False, timeout=10)
check("anon Add New Pet lands on login",
      r.status_code == 302 and "/login" in r.headers.get("Location", ""),
      r.headers.get("Location", ""))

# A signed-in viewer must never be shown a control that only leads to 403
r = viewer_sess.get(BASE + "/", timeout=10)
check("viewer nav hides Add New Pet", 'href="/pets/new"' not in r.text)
check("viewer dashboard offers no write CTA", "Add New Pet" not in r.text)

# =========================================================================
# 8. UI SURFACES THE RIGHT CONTROLS
# =========================================================================
print("--- UI surfaces ---")

r = admin_sess.get(BASE + "/", timeout=10)
check("admin nav shows User Management", "/users" in r.text and "User Management" in r.text)
check("admin user menu shows role", "Administrator" in r.text)

r = viewer_sess.get(BASE + "/", timeout=10)
check("viewer nav hides User Management", "User Management" not in r.text)
check("viewer sees Viewer badge", "Viewer" in r.text)

r = viewer_sess.get(BASE + "/pets/PET-0001", allow_redirects=False, timeout=10)
if r.status_code == 200:
    check("viewer pet details hides Edit/Delete",
          "Edit Record" not in r.text and "Delete Record" not in r.text)
else:
    check("viewer pet details loads", False, r.status_code)

# =========================================================================
print("=" * 50)
if failures:
    print("FAILURES:", failures)
    sys.exit(1)
print("ALL ROLE TESTS PASSED")
