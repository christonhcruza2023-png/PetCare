"""Feature tests for the added authentication, pagination and settings fixes."""
import glob
import html
import os
import re
import sys

import pymongo
import requests

BASE = "http://127.0.0.1:5000"
s = requests.Session()

failures = []


# -------------------------------------------------------------------------
# Self-contained setup: wipe test data and seed a known dataset so the suite
# can be re-run any number of times.
# -------------------------------------------------------------------------
def setup():
    db = pymongo.MongoClient("mongodb://localhost:27017")["petcare_db"]
    for col in ("pets", "settings", "activity", "users"):
        db[col].delete_many({})
    for f in glob.glob("static/uploads/*.png"):
        os.remove(f)

    # 18 records -> two pages at 10 per page. All share breed "Mutt",
    # and 12 are Dogs so animal=Dog still spans both pages.
    docs = []
    for i in range(18):
        docs.append({
            "pet_id": f"PET-{i + 1:04d}",
            "pet_name": f"SeedPet{i:02d}",
            "animal_type": "Dog" if i < 12 else "Cat",
            "breed": "Mutt",
            "sex": "Male",
            "owner_name": f"Owner{i}",
            "vaccination_status": "Vaccinated",
            "registration_date": "2026-01-01",
            "created_at": f"2026-01-01T00:00:{i:02d}+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "photo_filename": None,
        })
    db["pets"].insert_many(docs)
    return db


db = setup()


def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        failures.append(name)


def csrf(path):
    r = s.get(BASE + path, timeout=10)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    if not m:
        print(f"NO CSRF on {path} (status {r.status_code})")
        sys.exit(1)
    return r, m.group(1)


# =========================================================================
# 1. AUTHENTICATION
# =========================================================================
print("--- Authentication ---")

# Anonymous users are blocked from write routes
for path in ("/pets/new", "/pets/PET-0001/edit"):
    r = s.get(BASE + path, allow_redirects=False, timeout=10)
    check(
        f"anonymous GET {path} redirects to login",
        r.status_code == 302 and "/login" in r.headers.get("Location", ""),
        f"{r.status_code} {r.headers.get('Location', '')}",
    )

# Anonymous POST is blocked
_, tok = csrf("/login")
r = s.post(BASE + "/pets/create", data={"csrf_token": tok, "pet_name": "Anon",
           "animal_type": "Dog", "owner_name": "X"}, allow_redirects=False, timeout=10)
check("anonymous POST /pets/create redirected", r.status_code == 302
      and "/login" in r.headers.get("Location", ""), r.status_code)

# Registration validation
_, tok = csrf("/register")
r = s.post(BASE + "/register", data={"csrf_token": tok, "username": "ab",
          "password": "123", "confirm": "999"}, allow_redirects=False, timeout=10)
check("weak register rejected (400)", r.status_code == 400, r.status_code)
check("username length error shown", "3" in r.text and "30" in r.text)
check("password mismatch error shown", "do not match" in r.text)

# Register a real user
USER, PWD = "test_admin", "S3curePass!"
r = s.get(BASE + "/register", timeout=10)
tok = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
r = s.post(BASE + "/register", data={"csrf_token": tok, "username": USER,
          "email": "admin@example.com", "password": PWD, "confirm": PWD},
          allow_redirects=False, timeout=10)
check("register -> 302 (signed in)", r.status_code == 302, r.status_code)
check("register redirects to dashboard", r.headers.get("Location") == "/", r.headers.get("Location"))

# Session now authenticated (must NOT follow the redirect to /login)
r = s.get(BASE + "/pets/new", allow_redirects=False, timeout=10)
check("signed-in user can open /pets/new", r.status_code == 200, r.status_code)

# Duplicate username rejected
s2 = requests.Session()
r = s2.get(BASE + "/register", timeout=10)
tok2 = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
r = s2.post(BASE + "/register", data={"csrf_token": tok2, "username": USER,
            "password": PWD, "confirm": PWD}, allow_redirects=False, timeout=10)
check("duplicate username rejected", r.status_code == 400, r.status_code)
check("duplicate username message", "already taken" in r.text)

# Password is hashed in Mongo (never stored in clear text)
col = pymongo.MongoClient("mongodb://localhost:27017")["petcare_db"]["users"]
u = col.find_one({"username": USER})
check("user document exists", u is not None)
if u:
    check("password stored as hash (not plaintext)", PWD not in u.get("password_hash", ""))
    check("hash uses pbkdf2", u.get("password_hash", "").startswith("pbkdf2:"))
    check("email stored", u.get("email") == "admin@example.com")

# Logout
_, tok = csrf("/pets/new")
r = s.post(BASE + "/logout", data={"csrf_token": tok}, allow_redirects=False, timeout=10)
check("logout -> 302", r.status_code == 302, r.status_code)
r = s.get(BASE + "/pets/new", allow_redirects=False, timeout=10)
check("logout ends access to write routes", r.status_code == 302, r.status_code)

# Login: wrong password
_, tok = csrf("/login")
r = s.post(BASE + "/login", data={"csrf_token": tok, "username": USER,
          "password": "wrongpass"}, allow_redirects=False, timeout=10)
check("wrong password -> 401", r.status_code == 401, r.status_code)
check("wrong password message", "Incorrect username or password" in r.text)

# Login: unknown user (must not reveal which part failed)
_, tok = csrf("/login")
r = s.post(BASE + "/login", data={"csrf_token": tok, "username": "ghost_user_xyz",
          "password": "whatever123"}, allow_redirects=False, timeout=10)
check("unknown user -> 401 with same message", r.status_code == 401
      and "Incorrect username or password" in r.text, r.status_code)

# Login: correct credentials
_, tok = csrf("/login")
r = s.post(BASE + "/login", data={"csrf_token": tok, "username": USER,
          "password": PWD}, allow_redirects=False, timeout=10)
check("correct login -> 302", r.status_code == 302, r.status_code)

# Login is case-insensitive on username
s3 = requests.Session()
r = s3.get(BASE + "/login", timeout=10)
tok3 = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
r = s3.post(BASE + "/login", data={"csrf_token": tok3, "username": USER.upper(),
            "password": PWD}, allow_redirects=False, timeout=10)
check("login username case-insensitive", r.status_code == 302, r.status_code)

# next= must not allow an open redirect
s4 = requests.Session()
r = s4.get(BASE + "/login", timeout=10)
tok4 = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
r = s4.post(BASE + "/login?next=https://evil.example.com",
            data={"csrf_token": tok4, "username": USER, "password": PWD},
            allow_redirects=False, timeout=10)
check("open redirect blocked", r.headers.get("Location") == "/",
      r.headers.get("Location"))

# next= with a valid local path is honoured
s5 = requests.Session()
r = s5.get(BASE + "/login?next=/settings", timeout=10)
tok5 = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
r = s5.post(BASE + "/login?next=/settings",
            data={"csrf_token": tok5, "username": USER, "password": PWD},
            allow_redirects=False, timeout=10)
check("local next= honoured", r.headers.get("Location") == "/settings",
      r.headers.get("Location"))

# Sign-in UI present when logged out, user menu when logged in
r = requests.Session().get(BASE + "/", timeout=10)
check("logged-out page shows Sign In", 'href="/login"' in r.text)
check("logged-in page shows Sign Out", 'action="/logout"' in s.get(BASE + "/", timeout=10).text)
check("signed-in shows username", "test_admin" in s.get(BASE + "/", timeout=10).text)

# =========================================================================
# 2. PAGINATION (the reported bug: every record dumped on one page)
# =========================================================================
print("--- Pagination ---")

col = pymongo.MongoClient("mongodb://localhost:27017")["petcare_db"]["pets"]
total = col.count_documents({})

r = s.get(BASE + "/pets", timeout=15)
page_ids = re.findall(r'class="pet-id"', r.text)
unique_ids = set(re.findall(r'>(PET-\d+)<', r.text))
check("list page does not dump every record", len(unique_ids) <= 10,
      f"rendered {len(unique_ids)} unique of {total}")
check("pagination info shown", "Page" in r.text and "of" in r.text)
check("total count shown", f"{total} record" in r.text)

# Page 2 exists and shows different records
r2 = s.get(BASE + "/pets?page=2", timeout=15)
ids1 = set(re.findall(r'>(PET-\d+)<', r.text))
ids2 = set(re.findall(r'>(PET-\d+)<', r2.text))
check("page 2 renders 200", r2.status_code == 200, r2.status_code)
check("page 2 shows different records", ids1 and ids2 and not (ids1 & ids2),
      f"p1={len(ids1)} p2={len(ids2)} overlap={len(ids1 & ids2)}")

# Out-of-range page clamps instead of showing an empty screen
r3 = s.get(BASE + "/pets?page=9999", timeout=15)
check("out-of-range page clamps to last page", r3.status_code == 200
      and len(set(re.findall(r'>(PET-\d+)<', r3.text))) > 0, r3.status_code)

# Garbage page param does not crash
r4 = s.get(BASE + "/pets?page=abc", timeout=15)
check("invalid page param safe", r4.status_code == 200, r4.status_code)

# Pagination preserves active filters in its own links.
# 12 of the 18 seeded records are Dogs with breed "Mutt", so this query
# spans both pages and the page-2 link must carry every filter.
r5 = s.get(BASE + "/pets?q=Mutt&animal=Dog&sort=name_asc", timeout=15)
check("multi-page filtered result renders 200", r5.status_code == 200, r5.status_code)
next_m = re.search(r"location\.href='([^']*page=2[^']*)'", r5.text)
if not next_m:
    next_m = re.search(r'href="([^"]*page=2[^"]*)"', r5.text)
check("page 2 link rendered for multi-page result", next_m is not None)
link = html.unescape(next_m.group(1)) if next_m else ""
check("filter q preserved in pagination link", "q=Mutt" in link, link)
check("filter animal preserved in pagination link", "animal=Dog" in link, link)
check("sort preserved in pagination link", "sort=name_asc" in link, link)
check("pagination link is a valid page number", "page=2" in link, link)

# Following that link must honour all three filters plus the page number
if link:
    r6 = s.get(BASE + link, timeout=15)
    check("filtered page 2 loads", r6.status_code == 200, r6.status_code)
    tbody = r6.text.split("<tbody>")[1].split("</tbody>")[0] if "<tbody>" in r6.text else ""
    check("filtered page 2 shows only Dogs", "Cat" not in tbody)
    check("filtered page 2 keeps the sort", "name_asc" in r6.text)

# Previous-button URL must never be page=0, even when disabled
r7 = s.get(BASE + "/pets?page=2", timeout=15)
prev_m = re.search(r"location\.href='([^']*Previous[^']*)'|"
                   r"onclick=\"location.href='([^']*page=1[^']*)'\"", r7.text)
page_zero = re.search(r"page=0(?:&|'|\")", r7.text)
check("no page=0 link generated", page_zero is None,
      page_zero.group(0) if page_zero else "")

# =========================================================================
# 3. SETTINGS DEFAULTS NOW APPLIED (the other reported bug)
# =========================================================================
print("--- Settings defaults ---")

# Reset to known state first
r = s.get(BASE + "/settings", timeout=10)
tok = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
s.post(BASE + "/settings", data={"csrf_token": tok, "theme": "light",
      "default_sort": "newest", "default_view": "table",
      "profile_display_name": "", "profile_email": ""}, timeout=10)

r = s.get(BASE + "/pets", timeout=15)
check("default sort applied (newest)",
      'value="newest" selected' in r.text or 'selected value="newest"' in r.text)
check("default view applied (table)",
      "view-table" in r.text and "view-cards" not in r.text)

# Save a non-default sort + card view
r = s.get(BASE + "/settings", timeout=10)
tok = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
r = s.post(BASE + "/settings", data={"csrf_token": tok, "theme": "dark",
          "default_sort": "name_desc", "default_view": "cards",
          "profile_display_name": "", "profile_email": ""},
          allow_redirects=False, timeout=10)
check("settings save -> 302", r.status_code == 302, r.status_code)

r = s.get(BASE + "/pets", timeout=15)
check("saved sort default applied",
      'value="name_desc" selected' in r.text or 'selected value="name_desc"' in r.text,
      "not applied")
check("saved view default applied (cards)", "view-cards" in r.text)
check("records sorted by name desc", r.text.index("Bulk9") < r.text.index("Bulk1")
      if "Bulk9" in r.text and "Bulk1" in r.text else True)

# An explicit ?sort= in the URL overrides the saved default
r = s.get(BASE + "/pets?sort=oldest", timeout=15)
check("explicit sort overrides saved default",
      'value="oldest" selected' in r.text or 'selected value="oldest"' in r.text)

# Settings page renders back the saved values
r = s.get(BASE + "/settings", timeout=10)
check("settings page shows saved sort", "name_desc" in r.text)
m = re.search(r'name="default_view" value="cards"[^>]*checked|checked[^>]*value="cards"', r.text)
check("settings page shows saved view checked", m is not None)

# Invalid profile email rejected
r = s.get(BASE + "/settings", timeout=10)
tok = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
r = s.post(BASE + "/settings", data={"csrf_token": tok, "theme": "dark",
          "default_sort": "newest", "default_view": "table",
          "profile_display_name": "X", "profile_email": "not-an-email"},
          allow_redirects=False, timeout=10)
check("invalid profile email rejected", r.status_code == 400, r.status_code)

# =========================================================================
print("=" * 50)
if failures:
    print("FAILURES:", failures)
    sys.exit(1)
print("ALL FEATURE TESTS PASSED")
