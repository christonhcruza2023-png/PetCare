# 🐾 PetCare Management System

A complete, responsive **PetCare** website built with **HTML5, CSS3, vanilla JavaScript, Python, Flask, MongoDB (PyMongo), Jinja2 and Werkzeug**.

It lets pet owners, caretakers and staff **register, view, search, filter, edit and delete animal records** — including photo uploads, dashboard statistics computed live from MongoDB, and a working **light / dark mode** toggle.

> This is a real, working application with a connected database and functional CRUD — not a UI prototype.

---

## ✨ Features

- **Dashboard** — total pets, dogs, cats, other animals, recent records, recent activity. All numbers are computed from MongoDB, never hardcoded.
- **Complete CRUD** — create, view, edit and delete pet records.
- **User accounts** — register / sign in / sign out with **hashed passwords** (`werkzeug.security`, PBKDF2-SHA256). Browsing stays open to everyone.
- **Role-based permissions** — two roles with different powers:
  - **Administrator** — create, edit and delete pet records, plus full user management (promote, demote, delete accounts).
  - **Viewer** — read-only. Can browse, search and open pet profiles, but cannot change anything; write routes return a clear **403** page and the write buttons are hidden from the UI.
- **User management page** (`/users`) — administrators can promote/demote accounts between the two roles and delete accounts, with lock-out protection: the last administrator can be neither demoted nor deleted, and nobody can delete their own account while signed in.
- **Real pagination** — 10 records per page with Previous/Next controls, page info, and filters preserved across pages.
- **Saved preferences** — the default sort order and table/card display chosen on Settings are applied automatically on the Pet Records page (an explicit toolbar choice overrides them).
- **Pet photo upload** — JPG / JPEG / PNG / WEBP, 5 MB limit, client + server validation, live preview, secure unique filenames, old photo removed only after the new one is saved.
- **Search, filter & sort** — search by Pet ID, name, breed or owner; filter by animal type and vaccination status; sort by name or date.
- **Pet profile page** — full record with animal info, owner info, medical notes and timestamps.
- **Light / dark mode** — sun/moon toggle, persisted in `localStorage`, falls back to the OS preference, applied on every page with smooth transitions.
- **Settings page** — theme preference, default sort, default display, basic profile fields (persisted in MongoDB).
- **Security** — server-side validation, CSRF protection on every state-changing form, secure file uploads (magic-byte checks), POST-only deletes, secret key from environment variables, no credentials in source control.
- **Responsive** — sidebar on desktop, collapsible drawer on mobile, table on desktop, cards on mobile.
- **UX polish** — toast notifications, confirmation modal for destructive actions, loading spinner on submit, empty states, visible focus states, keyboard-navigable.

---

## 📁 Project structure

```
petcare/
├── app.py                  # Flask application + all routes
├── config.py               # Configuration loaded from environment variables
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template (no real credentials)
├── .gitignore
├── README.md
├── templates/
│   ├── base.html           # Shared layout: sidebar, topbar, toasts, modal
│   ├── dashboard.html      # Dashboard with dynamic stats
│   ├── pets.html           # Records list (search / filter / sort / pagination)
│   ├── add_pet.html        # Create form
│   ├── edit_pet.html       # Edit form (pre-filled)
│   ├── pet_details.html    # Pet profile
│   ├── login.html          # Sign in
│   ├── register.html       # Create account
│   ├── users.html          # User management (administrators only)
│   ├── settings.html       # Settings
│   ├── 403.html            # Access denied
│   ├── 404.html
│   └── 500.html
├── static/
│   ├── css/style.css       # Light + dark themes via CSS variables
│   ├── js/script.js        # Theme, sidebar, toasts, modal, validation, preview
│   ├── images/default-pet.png
│   └── uploads/            # Uploaded pet photos (git-ignored)
└── utils/
    └── validators.py       # Server-side form + file validation
```

---

## 🚀 Getting started

### 1. Requirements

- **Python 3.10+**
- **MongoDB** — either a local server or a free [MongoDB Atlas](https://www.mongodb.com/atlas) cluster

> **First run:** create an account at **/register** before adding any records — the create, edit and delete routes require an **Administrator** account. The very first account you register automatically becomes the administrator. Every account after that starts as a **Viewer** and can be promoted on the `/users` page.
>
> Alternatively, set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `.env` **before the first start** and that administrator is created for you (it only runs while the `users` collection is empty, so it can never overwrite an existing account).

### 2. Install MongoDB (choose one)

**Option A — Local MongoDB Community Server**

1. Download from <https://www.mongodb.com/try/download/community>
2. Install and start the service (it listens on `mongodb://localhost:27017` by default)

**Option B — MongoDB Atlas (cloud, free tier)**

1. Create a free cluster at <https://www.mongodb.com/atlas>
2. Create a database user and allow your IP address (or `0.0.0.0/0` for development)
3. Copy the connection string, e.g.
   `mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`

### 3. Set up the project (VS Code terminal)

```bash
# 1. Go into the project folder
cd PetCare

# 2. (Recommended) create a virtual environment
python -m venv .venv

#    • macOS / Linux
source .venv/bin/activate
#    • Windows PowerShell
.venv\Scripts\Activate.ps1
#    • Windows CMD
.venv\Scripts\activate.bat

# 3. Install the dependencies
pip install -r requirements.txt

# 4. Create your .env file from the template
copy .env.example .env        # Windows CMD
# cp .env.example .env        # macOS / Linux

# 5. Edit .env and set your values (at minimum SECRET_KEY and MONGO_URI)
```

`.env` example:

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=petcare_db
MONGO_COLLECTION=pets
SECRET_KEY=put-a-long-random-string-here
MAX_UPLOAD_MB=5
FLASK_DEBUG=1
```

Generate a strong secret key with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Run the application

```bash
python app.py
```

Then open **<http://127.0.0.1:5000/>** in your browser.

> The app creates the `petcare_db` database, the `pets` collection, and a **unique index on `pet_id`** automatically the first time it starts. The upload folder `static/uploads/` is created automatically as well.

---

## 🧭 Routes

| Method | Path                       | Purpose                     | Auth |
| ------ | -------------------------- | --------------------------- | ---- |
| GET    | `/`                        | Dashboard                   | —    |
| GET    | `/pets`                    | Pet records (search/filter/sort/pagination) | — |
| GET    | `/register`                | Create an account           | —    |
| POST   | `/register`                | Submit registration         | —    |
| GET    | `/login`                   | Sign in                     | —    |
| POST   | `/login`                   | Submit sign-in              | —    |
| POST   | `/logout`                  | Sign out                    | —    |
| GET    | `/pets/new`                | New pet form                | Admin |
| POST   | `/pets/create`             | Save a new pet              | Admin |
| GET    | `/pets/<pet_id>`           | Pet details                 | —    |
| GET    | `/pets/<pet_id>/edit`      | Edit form                   | Admin |
| POST   | `/pets/<pet_id>/update`    | Update the record           | Admin |
| POST   | `/pets/<pet_id>/delete`    | Delete (after confirmation) | Admin |
| GET    | `/users`                   | User management             | Admin |
| POST   | `/users/<user_id>/role`    | Promote / demote an account | Admin |
| POST   | `/users/<user_id>/delete`  | Delete an account           | Admin |
| GET/POST | `/settings`              | Settings                    | POST ✔ |

**Permission model**

| Action | Visitor (not signed in) | Viewer | Administrator |
| --- | --- | --- | --- |
| Dashboard, record list, pet profile, settings | ✔ | ✔ | ✔ |
| Create / edit / delete records | → sign in | ✖ 403 | ✔ |
| User management, roles | → sign in | ✖ 403 | ✔ |

Deletes **only** accept `POST`. A `GET` request to the delete URL returns `405`.
Routes behind a role redirect anonymous users to `/login?next=…` and return them
after a successful sign-in; a signed-in user with the wrong role gets a **403**
page explaining what their account is allowed to do. The `next` value is
restricted to local paths, so an open redirect is not possible.

### Pagination

`/pets?page=N` — 10 records per page (`PER_PAGE` in `config.py`). Out-of-range and
non-numeric page values are clamped instead of erroring. Active `q`, `animal`,
`vacc`, `sort` and `view` parameters are carried through every page link.

### Settings defaults

`default_sort` and `default_view` saved on `/settings` are applied whenever
`/pets` is opened without an explicit `sort=`/`view=` parameter. Choosing a value
in the records toolbar overrides the saved default for that visit only.

---

## 🗄️ MongoDB document shape

Database `petcare_db`, collection `pets`:

```json
{
  "_id": "…",
  "pet_id": "PET-0001",
  "pet_name": "Buddy",
  "animal_type": "Dog",
  "breed": "Golden Retriever",
  "sex": "Male",
  "date_of_birth": "2021-04-10",
  "estimated_age": "",
  "color": "Golden",
  "weight": 28.5,
  "owner_name": "Jane Doe",
  "owner_contact": "+1 555 010 2030",
  "owner_email": "jane@example.com",
  "owner_address": "12 Paw Street",
  "vaccination_status": "Vaccinated",
  "medical_notes": "Healthy",
  "photo_filename": "buddy_1a2b3c4d5e6f.png",
  "registration_date": "2025-02-12",
  "created_at": "2025-02-12T10:15:00+00:00",
  "updated_at": "2025-02-12T10:15:00+00:00"
}
```

Two extra collections are used: `settings` (app preferences) and `activity` (recent activity feed).

The `users` collection holds accounts:

```json
{
  "_id": "…",
  "username": "jane_doe",
  "username_lower": "jane_doe",
  "email": "jane@example.com",
  "password_hash": "pbkdf2:sha256:600000$salt$hash…",
  "display_name": "jane_doe",
  "role": "admin",
  "created_at": "2026-10-22T12:00:00+00:00",
  "updated_at": "2026-10-22T12:00:00+00:00"
}
```

`role` is either `"admin"` or `"viewer"`; anything else is treated as `viewer`,
so an unexpected value fails closed rather than open. `username` has a
**unique index**, so duplicate accounts are rejected at the database level as
well as in validation. Passwords are stored only as PBKDF2-SHA256 hashes —
never in clear text.

---

## 🎨 Theming

Light and dark palettes are defined as CSS custom properties in `static/css/style.css`:

| Token          | Light     | Dark      |
| -------------- | --------- | --------- |
| Background     | `#F8FAFC` | `#0F172A` |
| Cards          | `#FFFFFF` | `#1E293B` |
| Primary text   | `#1E293B` | `#F1F5F9` |
| Secondary text | `#64748B` | `#94A3B8` |
| Accent green   | `#16A34A` | `#4ADE80` |
| Borders        | `#E2E8F0` | `#334155` |

The active theme is written to `localStorage` under `petcare.theme`. On the very first visit (no stored value) the OS preference is used. An inline script in `<head>` applies the theme before first paint, so there is no flash of the wrong colours.

---

## 🔒 Security notes

- **CSRF** — `flask-wtf`'s `CSRFProtect` guards every `POST` route; each form embeds a `csrf_token`.
- **Passwords** — hashed with `werkzeug.security.generate_password_hash(..., method="pbkdf2:sha256")` and verified with `check_password_hash`. Sign-in returns the same *"Incorrect username or password"* message for an unknown user and a wrong password, so accounts cannot be enumerated by error text. Usernames are looked up case-insensitively.
- **Authorisation** — two layers on every state-changing route: `login_required` (are you signed in?) and `role_required(...)` (is your role allowed?). Record writes and user management require the **Administrator** role; anonymous visitors are redirected to sign in rather than shown a 403. Roles are re-read from MongoDB on every request via `before_request`, so a demotion takes effect immediately — there is no stale role cached in the session.
- **Lock-out protection** — the last administrator can be neither demoted nor deleted, and no one can delete their own account while signed in. These rules are enforced server-side, not just by disabling buttons.
- **Open redirect** — the `?next=` return URL is accepted only when it starts with a single `/`, so `//evil.example.com` or an absolute URL falls back to the dashboard.
- **File uploads** — extension allow-list **plus** magic-byte inspection (PNG / JPEG / WEBP signatures). Uploaded names are passed through `secure_filename` and given a random suffix, so the original filename is never trusted. Size is limited to 5 MB (also enforced globally via `MAX_CONTENT_LENGTH`).
- **Deletion safety** — photos are only removed from `static/uploads/`, never from arbitrary paths, and only after the database record is gone.
- **Secrets** — `SECRET_KEY` and `MONGO_URI` come from environment variables; `.env` is git-ignored. `.env.example` contains placeholders only.
- **Input validation** — every field is validated on the server (`utils/validators.py`) even though the client also validates.
- **Errors** — custom `404` and `500` pages; missing records are handled gracefully instead of crashing.

### Production hardening suggestions

1. Set `FLASK_DEBUG=0` and serve with a production WSGI server, e.g. `gunicorn -w 4 "app:app"` (Linux/macOS) or `waitress-serve --host=0.0.0.0 --port=5000 app:app` (Windows).
2. Rate-limit `/login` and `/register`, store sessions server-side (Redis / MongoDB), and set secure cookie flags (`SESSION_COOKIE_SECURE`, `HTTPONLY`, `SAMESITE=Lax`).
3. Add password reset, e-mail verification and role-based permissions (e.g. admin vs. viewer) as the user base grows.
4. Move uploaded photos to object storage — **AWS S3**, **Cloudinary**, **Cloudflare R2** or **Azure Blob Storage** — and store only the returned URL/key in `photo_filename`. Serve them via a signed URL or a CDN so `static/uploads/` no longer grows on the web server.
5. Keep MongoDB behind a firewall with authentication enabled and least-privilege users.

---

## 🐛 Troubleshooting

| Symptom | Fix |
| --- | --- |
| Redirected to `/login` when adding a pet | Working as intended — sign in first, or create an account at `/register`. |
| **403 "Access denied"** when adding a pet | Your account is a **Viewer**. Sign in as an administrator and promote it on `/users`, or register a fresh account if the install is brand new (the first account is the admin). |
| `/users` returns 403 | User management is administrator-only. |
| "You are the only administrator…" when changing a role | Lock-out protection. Promote another account to administrator first, then demote this one. |
| `"That username is already taken"` | The username already exists in the `users` collection. Pick another, or sign in instead. |
| **`ERROR: Port 5000 is already in use.`** on start-up | Another copy of PetCare is already running. The app now **refuses to start** rather than let two servers share the port (on Windows two processes *can* bind the same port, which silently serves requests from old code and produces random 500s). Stop the other instance (`CTRL+C` in its terminal, or `netstat -ano \| findstr :5000` then `taskkill /F /PID <pid>`) and start again — or use `PORT=5001 python app.py`. |
| `Could not build url for endpoint` / `GET /` returns 500 after edits | Almost always a stale process serving old code. Look for more than one listener on port 5000 (`netstat -ano \| findstr :5000`), stop them all, and start one fresh instance. |
| **The delete confirmation modal is visible on page load** | Should never happen now — the fix is the global `[hidden] { display: none !important; }` rule in `style.css`. If you see it, hard-refresh (`Ctrl+F5`) so the browser re-fetches the cached stylesheet. |
| `ServerSelectionTimeoutError` / "Could not reach MongoDB" | MongoDB is not running. Start the service, or check `MONGO_URI` in `.env`. For Atlas, allow your IP and check the username/password. |
| `ModuleNotFoundError: No module named 'flask'` | The virtual environment is not activated, or dependencies are not installed. Re-run `pip install -r requirements.txt`. |
| `Address already in use` on port 5000 | Another process is using the port. Run `PORT=5001 python app.py`, or stop the other process. |
| Photo does not upload | Must be JPG/JPEG/PNG/WEBP and under 5 MB. Check the flash message — the server validates the file's magic bytes too. |
| `BadSecretKey` / session errors | `SECRET_KEY` is missing or empty in `.env`. Set a long random value. |
| Changes to templates not appearing | Restart `python app.py`. With `FLASK_DEBUG=1` templates auto-reload, but Python changes always need a restart. |
| Uploaded files lost after redeploy | `static/uploads/` is git-ignored by design. Use object storage (see Production hardening) for real deployments. |

## 🧪 Testing

Two test scripts are included in the project root:

```bash
# Role-based permission tests: admin vs viewer, user management
python tests_roles.py

# Feature tests: auth, pagination, saved-settings defaults
python tests_features.py

# CRUD / upload / security regression suite
python pet_e2e.py
```

All three expect the app to be running on `http://127.0.0.1:5000`. Each suite
resets the `petcare_db` test data it uses, so they can be re-run freely. A
shared local MongoDB on the default port is required. Run them in this order —
each one wipes the accounts the previous one created.

---

## 🧪 Manual test checklist

- [x] Register an account, sign out, sign back in.
- [x] Anonymous users are redirected to `/login` when opening a write route, then returned after signing in.
- [x] Wrong password and unknown username both show the same generic error.
- [x] **First account registered becomes the Administrator; later accounts are Viewers.**
- [x] **Viewer: can read everything, gets 403 on write routes, and sees no Edit/Delete/Add controls.**
- [x] **Administrator: full CRUD plus the `/users` page (promote, demote, delete).**
- [x] **Last administrator cannot be demoted or deleted; nobody can delete their own account.**
- [x] **Demoting a signed-in user revokes their write access on their very next request.**
- [x] Create a pet with a photo → record appears on the dashboard and the details page.
- [x] Restart the app → records are still there (they live in MongoDB).
- [x] Search by name / breed / Pet ID / owner.
- [x] Filter by animal type and vaccination status; sort by name or date.
- [x] Sort/display preferences saved on Settings are applied on `/pets`.
- [x] Long lists paginate — 10 per page, Previous/Next, filters preserved.
- [x] Edit a pet without uploading a photo → the existing photo stays.
- [x] Edit a pet and upload a new photo → the new photo replaces the old one (old file is removed from disk).
- [x] Delete → confirmation modal → record and its photo are removed.
- [x] Try a `GET` on a delete URL → refused (`405`).
- [x] Upload an `.exe` or a renamed file → rejected.
- [x] Visit `/pets/PET-9999` → friendly 404 page, no crash.
- [x] Toggle light/dark on every page; reload → preference persists; first visit uses the OS theme.
- [x] Resize to mobile → sidebar collapses, table becomes cards.
- [x] **The delete-confirmation modal is NOT visible on page load** — it only appears after clicking a Delete button, and closes on Cancel, backdrop click or `Esc`.
- [x] **Photo upload preview box is hidden** until a file is actually chosen.
- [x] Starting a second `python app.py` exits immediately with a clear port-in-use message instead of leaving two servers on port 5000.

---

## 📄 License

Free to use for school projects and learning purposes.
