"""End-to-end smoke test for PetCare."""
import io, os, re, sys
import requests

BASE = "http://127.0.0.1:5000"
s = requests.Session()

def csrf(path):
    r = s.get(BASE + path, timeout=10)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    if not m:
        print("NO CSRF on", path, "status", r.status_code); sys.exit(1)
    return r, m.group(1)

failures = []

def list_pets_count():
    """Count rows currently shown on the records page."""
    rr = s.get(BASE + "/pets", timeout=10)
    return rr.text.count('class="pet-id"')

def check(name, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {extra}")
    if not cond:
        failures.append(name)

# --- 0. Authenticate (write routes are login-protected) ---
E2E_USER, E2E_PASS = "e2e_runner", "E2ePass!42"
r = s.get(BASE + "/register", timeout=10)
tok = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
r = s.post(BASE + "/register", data={"csrf_token": tok, "username": E2E_USER,
          "password": E2E_PASS, "confirm": E2E_PASS}, allow_redirects=False,
          timeout=10)
if r.status_code != 302:  # already exists from an earlier run -> log in
    r = s.get(BASE + "/login", timeout=10)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
    r = s.post(BASE + "/login", data={"csrf_token": tok, "username": E2E_USER,
              "password": E2E_PASS}, allow_redirects=False, timeout=10)
check("authenticated as write-user", r.status_code == 302, f"got {r.status_code}")
r = s.get(BASE + "/pets/new", allow_redirects=False, timeout=10)
check("session can reach write routes", r.status_code == 200, f"got {r.status_code}")

# --- 1. Dashboard ---
r = s.get(BASE + "/", timeout=10)
check("GET / dashboard 200", r.status_code == 200, f"got {r.status_code}")

# --- 2. Pet list ---
r = s.get(BASE + "/pets", timeout=10)
check("GET /pets 200", r.status_code == 200, f"got {r.status_code}")

# --- 3. New form ---
r, token = csrf("/pets/new")
check("GET /pets/new 200", r.status_code == 200, f"got {r.status_code}")

# --- 4. Create (with photo) ---
png = open("static/images/default-pet.png", "rb").read()
files = {"photo": ("buddy.png", io.BytesIO(png), "image/png")}
data = {
    "csrf_token": token,
    "pet_name": "Buddy",
    "animal_type": "Dog",
    "breed": "Golden Retriever",
    "sex": "Male",
    "date_of_birth": "2021-04-10",
    "color": "Golden",
    "weight": "28.5",
    "owner_name": "Jane Doe",
    "owner_contact": "+1 555 010 2030",
    "owner_email": "jane@example.com",
    "owner_address": "12 Paw Street",
    "vaccination_status": "Vaccinated",
    "medical_notes": "Healthy",
    "registration_date": "2025-02-12",
}
r = s.post(BASE + "/pets/create", data=data, files=files, allow_redirects=False, timeout=15)
check("POST /pets/create redirects", r.status_code == 302, f"got {r.status_code}")
loc = r.headers.get("Location", "/pets/?")
check("unique pet_id generated", "PET-0001" in loc, loc)

pet_id = loc.rstrip("/").split("/")[-1]

# --- 5. Details ---
r = s.get(f"{BASE}/pets/{pet_id}", timeout=10)
check("details page shows record", r.status_code == 200 and "Buddy" in r.text, f"got {r.status_code}")

# --- 6. Uploaded photo exists on disk ---
uploads = [f for f in os.listdir("static/uploads") if f.endswith(".png")]
check("photo saved to static/uploads", len(uploads) >= 1, str(uploads))
photo_name = uploads[0] if uploads else ""
if photo_name:
    r = s.get(f"{BASE}/static/uploads/{photo_name}", timeout=10)
    check("photo served over HTTP 200", r.status_code == 200, f"got {r.status_code}")

# --- 7. Dashboard reflects the new record ---
r = s.get(BASE + "/", timeout=10)
check("dashboard total = 1", ">1<" in re.sub(r"\s+", " ", r.text) and "Total Registered Pets" in r.text)

# --- 8. Validation: required fields missing ---
_, token2 = csrf("/pets/new")
r = s.post(BASE + "/pets/create", data={"csrf_token": token2, "pet_name": "", "animal_type": ""},
          allow_redirects=False, timeout=10)
check("invalid create returns 400", r.status_code == 400, f"got {r.status_code}")
check("validation message shown", b"required" in r.content.lower())

# --- 9. Validation: bad file type ---
_, token3 = csrf("/pets/new")
bad = {"csrf_token": token3, "pet_name": "Bad", "animal_type": "Dog", "owner_name": "X"}
files_bad = {"photo": ("evil.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")}
r = s.post(BASE + "/pets/create", data=bad, files=files_bad, allow_redirects=False, timeout=10)
check("rejects .exe upload (400)", r.status_code == 400, f"got {r.status_code}")

# --- 10. Edit (no new photo) keeps existing photo ---
r, token4 = csrf(f"/pets/{pet_id}/edit")
check("GET edit 200", r.status_code == 200, f"got {r.status_code}")
data["csrf_token"] = token4
data["pet_name"] = "Buddy Updated"
r = s.post(BASE + f"/pets/{pet_id}/update", data=data, allow_redirects=False, timeout=10)
check("POST update 302", r.status_code == 302, f"got {r.status_code}")
r = s.get(f"{BASE}/pets/{pet_id}", timeout=10)
check("edit persisted", "Buddy Updated" in r.text)
check("old photo preserved", photo_name in r.text, "photo link present")

# --- 11. Edit (with replacement photo) ---
_, token5 = csrf(f"/pets/{pet_id}/edit")
png2 = open("static/images/default-pet.png", "rb").read()
files = {"photo": ("new_photo.png", io.BytesIO(png2), "image/png")}
r = s.post(BASE + f"/pets/{pet_id}/update", data=data, files=files, allow_redirects=False, timeout=10)
check("update with new photo 302", r.status_code == 302, f"got {r.status_code}")

# The record must now point at the NEW file, and the old file must be gone.
new_photos = [f for f in os.listdir("static/uploads") if f.startswith("new_photo_")]
check("replacement photo stored on disk", len(new_photos) == 1, str(new_photos))
new_photo_name = new_photos[0] if new_photos else ""
r = s.get(f"{BASE}/pets/{pet_id}", timeout=10)
check("record points at replacement photo",
      new_photo_name in r.text and photo_name not in r.text)
check("old photo file removed from disk", photo_name not in os.listdir("static/uploads"))
if new_photo_name:
    r = s.get(f"{BASE}/static/uploads/{new_photo_name}", timeout=10)
    check("replacement photo served 200", r.status_code == 200, f"got {r.status_code}")
photo_name = new_photo_name  # subsequent delete must remove THIS file

# --- 12. Search / filter / sort ---
r = s.get(BASE + "/pets?q=Buddy", timeout=10)
check("search by name returns record", "Buddy" in r.text)
r = s.get(BASE + "/pets?q=ZZZZZZNOMATCH", timeout=10)
check("empty state on no match", "No matching records" in r.text)
r = s.get(BASE + "/pets?animal=Dog&vacc=Vaccinated&sort=name_asc", timeout=10)
check("filters+sort respond", r.status_code == 200, f"got {r.status_code}")

# --- 13. GET delete is refused ---
r = s.get(BASE + f"/pets/{pet_id}/delete", allow_redirects=False, timeout=10)
check("GET delete not allowed (405)", r.status_code in (404, 405), f"got {r.status_code}")

# --- 14. Settings GET/POST ---
r, token6 = csrf("/settings")
check("GET /settings 200", r.status_code == 200, f"got {r.status_code}")
r = s.post(BASE + "/settings", data={"csrf_token": token6, "theme": "dark",
           "default_sort": "newest", "default_view": "cards",
           "profile_display_name": "Cust", "profile_email": "a@b.com"},
           allow_redirects=False, timeout=10)
check("POST /settings 302", r.status_code == 302, f"got {r.status_code}")

# --- 15. 404 page for missing pet ---
r = s.get(BASE + "/pets/PET-9999", timeout=10)
check("missing pet -> 404", r.status_code == 404, f"got {r.status_code}")

# --- 16. 404 page for unknown route ---
r = s.get(BASE + "/no/such/page", timeout=10)
check("unknown route -> 404", r.status_code == 404, f"got {r.status_code}")

# --- 17. CSRF guard: POST without token refused ---
before = list_pets_count()
r = s.post(BASE + "/pets/create", data={"pet_name": "NoToken", "animal_type": "Dog"},
          allow_redirects=False, timeout=10)
check("CSRF-less POST not 200 (400/302)", r.status_code in (400, 302), f"got {r.status_code}")
after = list_pets_count()
check("CSRF-less POST created no record", before == after, f"{before} -> {after}")

# --- 18. Delete ---
r, token7 = csrf(f"/pets/{pet_id}/edit")
r = s.post(BASE + f"/pets/{pet_id}/delete", data={"csrf_token": token7},
          allow_redirects=False, timeout=10)
check("POST delete 302", r.status_code == 302, f"got {r.status_code}")
r = s.get(f"{BASE}/pets/{pet_id}", timeout=10)
check("deleted pet -> 404", r.status_code == 404, f"got {r.status_code}")

# --- 19. Uploads dir emptied of that file ---
left = [f for f in os.listdir("static/uploads")]
check("upload cleaned on delete", photo_name not in left, str(left))

print("=" * 50)
if failures:
    print("FAILURES:", failures)
    sys.exit(1)
print("ALL TESTS PASSED")
