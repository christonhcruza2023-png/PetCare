"""PetCare — a Flask + MongoDB pet record management system.

Run it with:

    python app.py

Routes follow the specification in the project brief:

    GET  /                        Dashboard
    GET  /pets                    Pet records list
    GET  /pets/new                New pet form
    POST /pets/create             Save a new pet
    GET  /pets/<pet_id>           Pet details
    GET  /pets/<pet_id>/edit      Edit form
    POST /pets/<pet_id>/update    Update a pet
    POST /pets/<pet_id>/delete    Delete a pet (confirmation modal)
    GET  /settings                Settings page
    POST /settings                Save settings
"""

from __future__ import annotations

import math
import os
import re
import secrets
from datetime import date, datetime, timezone
from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Config
from utils.validators import (
    ANIMAL_TYPES,
    EMAIL_RE,
    SEX_OPTIONS,
    VACCINATION_OPTIONS,
    extension_of,
    validate_image_file,
    validate_login,
    validate_pet_form,
    validate_registration,
)

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
#
#   admin   – full control: create / edit / delete records and manage users
#   viewer  – read-only: dashboard, record list and record details
#
ADMIN = "admin"
VIEWER = "viewer"
ROLES = (ADMIN, VIEWER)
ROLE_LABELS = {ADMIN: "Administrator", VIEWER: "Viewer"}


def role_of(user) -> str:
    """Return a safe role for a user document (unknown values become viewer)."""
    role = (user or {}).get("role") or VIEWER
    return role if role in ROLES else VIEWER

# ---------------------------------------------------------------------------
# App factory / core setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config.from_object(Config)

csrf = CSRFProtect(app)

# Ensure the upload folder exists before anything tries to write to it.
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


def _connect_mongo():
    """Create the PyMongo client with a short server-selection timeout."""
    client = MongoClient(
        app.config["MONGO_URI"],
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
    )
    return client


client = _connect_mongo()
db = client[app.config["MONGO_DB_NAME"]]
pets = db[app.config["MONGO_COLLECTION"]]
settings_col = db[app.config["MONGO_SETTINGS_COLLECTION"]]
users = db["users"]

# Unique pet_id index (safe to call on every start-up).
try:
    pets.create_index([("pet_id", ASCENDING)], unique=True)
    pets.create_index([("created_at", DESCENDING)])
    users.create_index([("username", ASCENDING)], unique=True)
except PyMongoError:  # pragma: no cover - index creation is best-effort
    app.logger.warning("Could not create MongoDB indexes.")


def bootstrap_admin() -> None:
    """Create the initial administrator when one is configured in `.env`.

    Only runs while the `users` collection is empty, so it can never
    overwrite an existing account. If no `ADMIN_USERNAME`/`ADMIN_PASSWORD`
    is configured, the first self-registered account becomes the admin
    instead (see the `register` route).
    """
    username = app.config.get("ADMIN_USERNAME", "").strip()
    password = app.config.get("ADMIN_PASSWORD", "")
    if not username or not password:
        return
    try:
        if users.count_documents({}) > 0:
            return
        if users.find_one({"username_lower": username.lower()}) is not None:
            return
        users.insert_one(
            {
                "username": username,
                "username_lower": username.lower(),
                "email": "",
                "password_hash": generate_password_hash(
                    password, method="pbkdf2:sha256"
                ),
                "display_name": username,
                "role": ADMIN,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
        )
        app.logger.info("Bootstrap administrator '%s' created.", username)
    except (PyMongoError, DuplicateKeyError):
        app.logger.warning("Could not create the bootstrap administrator.")


bootstrap_admin()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    """UTC timestamp in ISO-8601 form (MongoDB friendly)."""
    return datetime.now(timezone.utc).isoformat()


def today_str() -> str:
    return date.today().isoformat()


def generate_pet_id() -> str:
    """Return a unique, human-readable id such as ``PET-0042``."""
    last = pets.find_one({}, sort=[("_id", DESCENDING)])
    seq = 1
    if last and last.get("pet_id"):
        match = re.search(r"(\d+)", str(last["pet_id"]))
        if match:
            seq = int(match.group(1)) + 1
    # Retry if (extremely unlikely) a collision happens.
    for _ in range(50):
        candidate = f"PET-{seq:04d}"
        if pets.find_one({"pet_id": candidate}, {"_id": 1}) is None:
            return candidate
        seq += 1
    return f"PET-{secrets.token_hex(3).upper()}"


def serialize_pet(doc: dict | None) -> dict | None:
    """Convert a Mongo document into a template-friendly dict."""
    if not doc:
        return None
    doc = dict(doc)
    doc["_id"] = str(doc["_id"])
    if not doc.get("photo_filename"):
        doc["photo_filename"] = None
    return doc


def pet_url(pet: dict) -> str:
    return url_for("pet_details", pet_id=pet["pet_id"])


def human_date(value) -> str:
    """Format an ISO date string for display (e.g. ``12 Feb 2025``)."""
    if not value:
        return "—"
    try:
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y")
    except ValueError:
        return str(value)


def days_ago(timestamp) -> str:
    """Return a friendly ``3 days ago`` string from an ISO/datetime value."""
    if not timestamp:
        return ""
    try:
        dt = timestamp
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} min ago"
        hours = seconds // 3600
        if hours < 24:
            return f"{hours} h ago"
        days = seconds // 86400
        if days < 30:
            return f"{days} day(s) ago"
        return human_date(dt)
    except (ValueError, TypeError):
        return ""


app.jinja_env.globals.update(
    pet_url=pet_url,
    human_date=human_date,
    days_ago=days_ago,
)


def save_upload(file_storage) -> str:
    """Save an uploaded photo and return its stored filename.

    The original filename is never trusted: `secure_filename` is applied and a
    random suffix guarantees a unique, collision-free name.
    """
    ext = extension_of(file_storage.filename) or "png"
    stem = secure_filename(file_storage.filename.rsplit(".", 1)[0]) or "pet"
    stem = re.sub(r"[^A-Za-z0-9_-]", "", stem)[:40] or "pet"
    filename = f"{stem}_{secrets.token_hex(6)}.{ext}"
    # `werkzeug.utils.secure_filename` fallback if the helper import fails.
    target = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file_storage.save(target)
    return filename


def delete_upload(filename: str | None) -> None:
    """Remove an uploaded photo belonging to a pet record (never raises)."""
    if not filename:
        return
    # Only ever delete files that live inside the uploads folder.
    safe = os.path.basename(filename)
    if safe != filename:
        return
    target = os.path.join(app.config["UPLOAD_FOLDER"], safe)
    try:
        if os.path.isfile(target):
            os.remove(target)
    except OSError:  # pragma: no cover - defensive
        app.logger.warning("Could not delete uploaded file: %s", safe)


def add_activity(action: str, detail: str) -> None:
    """Append an entry to the `activity` collection (best effort)."""
    try:
        db["activity"].insert_one(
            {"action": action, "detail": detail, "created_at": now_iso()}
        )
    except PyMongoError:  # pragma: no cover - activity is non-critical
        app.logger.warning("Could not record activity.")


def allowed_ext(filename: str) -> bool:
    return extension_of(filename) in app.config["ALLOWED_EXTENSIONS"]


@app.context_processor
def inject_globals():
    """Make navigation helpers available to every template."""
    return {
        "request": request,
        "active_nav": request.path,
        "ANIMAL_TYPES": ANIMAL_TYPES,
        "SEX_OPTIONS": SEX_OPTIONS,
        "VACCINATION_OPTIONS": VACCINATION_OPTIONS,
        "TODAY": today_str(),
        "DEFAULT_PHOTO": url_for("static", filename="images/default-pet.png"),
        "WRITE_ROUTES": (
            "/pets/new",
            "/pets/create",
            "/pets/<pet_id>/edit",
            "/pets/<pet_id>/update",
            "/pets/<pet_id>/delete",
        ),
    }


def flash_errors(errors: dict) -> None:
    """Flash each validation error as a toast notification."""
    for field, message in errors.items():
        flash(message, "error")


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def load_user(user_id: str):
    """Fetch the currently signed-in user from their stored session id."""
    if not user_id:
        return None
    try:
        return users.find_one({"_id": ObjectId(user_id)})
    except (InvalidId, TypeError):
        return None


@app.before_request
def _attach_current_user():
    """Make `g.user` (the signed-in user) available to every request."""
    g.user = load_user(session.get("user_id"))


@app.context_processor
def inject_current_user():
    """Expose the signed-in user, their role and helpers to all templates."""
    user = getattr(g, "user", None)
    role = role_of(user)
    return {
        "current_user": user,
        "current_role": role,
        "role_label": ROLE_LABELS[role],
        "is_admin": role == ADMIN,
        "ROLES": ROLES,
        "ROLE_LABELS": ROLE_LABELS,
    }


def login_required(view):
    """Redirect anonymous users to the sign-in page for protected routes."""
    from functools import wraps

    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, "user", None) is not None:
            return view(*args, **kwargs)
        flash("Please sign in to manage pet records.", "error")
        # Remember where the user was headed so we can send them back.
        target = request.full_path if request.query_string else request.path
        return redirect(url_for("login", next=target))

    return wrapped


def role_required(*allowed_roles):
    """Require a signed-in user whose role is in `allowed_roles`.

    * Anonymous visitors are redirected to the sign-in page (so they are not
      shown a scary 403 before they have had a chance to log in).
    * Signed-in users without the right role receive a 403 page.
    """
    from functools import wraps

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = getattr(g, "user", None)
            if user is None:
                flash("Please sign in to manage pet records.", "error")
                target = request.full_path if request.query_string else request.path
                return redirect(url_for("login", next=target))

            if role_of(user) not in allowed_roles:
                allowed = ", ".join(ROLE_LABELS.get(r, r) for r in allowed_roles)
                flash(
                    f"Your account ({ROLE_LABELS[role_of(user)]}) does not have "
                    f"permission for that action. Required: {allowed}.",
                    "error",
                )
                return render_template(
                    "403.html",
                    required_roles=allowed_roles,
                    page_title="Access Denied",
                ), 403

            return view(*args, **kwargs)

        return wrapped

    return decorator


# Convenience alias used by the record write routes.
admin_required = role_required(ADMIN)


def safe_next_url(target) -> str:
    """Only ever redirect to a local path (prevents open-redirect attacks)."""
    if not target:
        return url_for("dashboard")
    if not target.startswith("/") or target.startswith("//"):
        return url_for("dashboard")
    return target


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user is not None:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        data, errors = validate_registration(request.form)
        if errors:
            flash_errors(errors)
            return render_template(
                "register.html",
                form=request.form.to_dict(),
                errors=errors,
                page_title="Create Account",
            ), 400

        password_hash = generate_password_hash(data["password"], method="pbkdf2:sha256")

        # The very first account becomes the administrator, so a fresh
        # install always has someone who can manage records and users.
        # (Setting ADMIN_USERNAME/ADMIN_PASSWORD in .env pre-creates one
        # instead — see `bootstrap_admin`.)
        is_first_user = users.count_documents({}) == 0
        role = ADMIN if is_first_user else VIEWER

        doc = {
            "username": data["username"],
            "username_lower": data["username"].lower(),
            "email": data["email"],
            "password_hash": password_hash,
            "display_name": data["username"],
            "role": role,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        try:
            users.insert_one(doc)
        except DuplicateKeyError:
            flash("That username is already taken. Please choose another.", "error")
            return render_template(
                "register.html",
                form=request.form.to_dict(),
                errors={"username": "That username is already taken."},
                page_title="Create Account",
            ), 400
        except PyMongoError:
            app.logger.exception("Could not create user")
            flash("Could not create the account. Please try again.", "error")
            return render_template(
                "register.html",
                form=request.form.to_dict(),
                errors={},
                page_title="Create Account",
            ), 500

        session.clear()
        session["user_id"] = str(doc["_id"])
        session["username"] = doc["username"]
        session.permanent = True

        add_activity("account", f"{doc['username']} created an account ({ROLE_LABELS[role]}).")
        if role == ADMIN:
            flash(
                f"Welcome, {doc['username']}! You are the first account, so it "
                f"has been set up as an Administrator.",
                "success",
            )
        else:
            flash(f"Welcome, {doc['username']}! Your account is ready.", "success")
        return redirect(safe_next_url(request.args.get("next")))

    return render_template(
        "register.html", form={}, errors={}, page_title="Create Account"
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        data, errors = validate_login(request.form)
        if errors:
            flash_errors(errors)
            return render_template(
                "login.html",
                form=request.form.to_dict(),
                errors=errors,
                page_title="Sign In",
            ), 400

        # Lookup is case-insensitive thanks to the stored `username_lower`.
        user = users.find_one({"username_lower": data["username"].lower()})
        if user is None or not check_password_hash(
            user.get("password_hash", ""), data["password"]
        ):
            # Same message whether the username or the password was wrong,
            # so an attacker cannot enumerate accounts.
            flash("Incorrect username or password. Please try again.", "error")
            return render_template(
                "login.html",
                form=request.form.to_dict(),
                errors={"password": "Incorrect username or password."},
                page_title="Sign In",
            ), 401

        session.clear()
        session["user_id"] = str(user["_id"])
        session["username"] = user["username"]
        session.permanent = True

        flash(f"Welcome back, {user['username']}!", "success")
        return redirect(safe_next_url(request.args.get("next")))

    return render_template("login.html", form={}, errors={}, page_title="Sign In")


@app.route("/logout", methods=["POST"])
def logout():
    username = session.get("username")
    session.clear()
    if username:
        flash(f"Signed out. See you soon, {username}!", "success")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# User administration (administrators only)
# ---------------------------------------------------------------------------


def count_admins(exclude_id=None) -> int:
    """Count active administrators, optionally ignoring one user id."""
    query = {"role": ADMIN}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    return users.count_documents(query)


@app.route("/users")
@role_required(ADMIN)
def user_list():
    """List every account so an administrator can manage it."""
    try:
        records = list(users.find().sort("created_at", ASCENDING))
    except PyMongoError:
        records = []
        flash("Could not load users from MongoDB.", "error")

    # How many records each account has touched (nice-to-have context).
    return render_template(
        "users.html",
        records=records,
        current_role=role_of(g.user),
        page_title="User Management",
    )


@app.route("/users/<user_id>/role", methods=["POST"])
@role_required(ADMIN)
def user_set_role(user_id: str):
    """Promote or demote an account."""
    target = _find_user_or_404(user_id)
    if target is None:
        return redirect(url_for("user_list"))

    new_role = (request.form.get("role") or "").strip()
    if new_role not in ROLES:
        flash("Unknown role. Choose Administrator or Viewer.", "error")
        return redirect(url_for("user_list"))

    old_role = role_of(target)
    if new_role == old_role:
        flash("That account already has that role.", "info")
        return redirect(url_for("user_list"))

    # Never allow the last administrator to demote themselves — that would
    # lock everyone out of managing the system.
    if old_role == ADMIN and new_role != ADMIN:
        if str(target["_id"]) == str(g.user["_id"]) and count_admins() <= 1:
            flash(
                "You are the only administrator, so you cannot remove your own "
                "admin rights. Promote another account first.",
                "error",
            )
            return redirect(url_for("user_list"))
        if count_admins(exclude_id=target["_id"]) == 0:
            flash(
                "At least one administrator must remain. Promote another account "
                "before demoting this one.",
                "error",
            )
            return redirect(url_for("user_list"))

    try:
        users.update_one(
            {"_id": target["_id"]},
            {"$set": {"role": new_role, "updated_at": now_iso()}},
        )
    except PyMongoError:
        flash("Could not update that role. Please try again.", "error")
        return redirect(url_for("user_list")), 500

    add_activity(
        "role",
        f"{target['username']} is now a {ROLE_LABELS[new_role].lower()}.",
    )
    flash(f"{target['username']} is now a {ROLE_LABELS[new_role]}.", "success")
    return redirect(url_for("user_list"))


@app.route("/users/<user_id>/delete", methods=["POST"])
@role_required(ADMIN)
def user_delete(user_id: str):
    """Delete an account (administrators only)."""
    target = _find_user_or_404(user_id)
    if target is None:
        return redirect(url_for("user_list"))

    if str(target["_id"]) == str(g.user["_id"]):
        flash("You cannot delete your own account while signed in.", "error")
        return redirect(url_for("user_list"))

    # Lock-out protection: never delete the final administrator.
    if role_of(target) == ADMIN and count_admins(exclude_id=target["_id"]) == 0:
        flash(
            "This is the last administrator account and cannot be deleted. "
            "Promote another account first.",
            "error",
        )
        return redirect(url_for("user_list"))

    try:
        result = users.delete_one({"_id": target["_id"]})
        if result.deleted_count == 0:
            raise PyMongoError("nothing deleted")
    except PyMongoError:
        flash("Could not delete that account. Please try again.", "error")
        return redirect(url_for("user_list")), 500

    add_activity("account", f"{target['username']}'s account was removed.")
    flash(f"Account “{target['username']}” was deleted.", "success")
    return redirect(url_for("user_list"))


def _find_user_or_404(user_id: str):
    """Load a user by id or return `None` after flashing a friendly error."""
    try:
        target = users.find_one({"_id": ObjectId(user_id)})
    except (InvalidId, TypeError):
        target = None
    if target is None:
        flash("That account no longer exists.", "error")
    return target


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.route("/")
def dashboard():
    try:
        pets_list = list(pets.find().sort("created_at", DESCENDING))
    except PyMongoError:
        pets_list = []
        flash("Could not reach MongoDB. Showing an empty dashboard.", "error")

    total = len(pets_list)
    dogs = sum(1 for p in pets_list if p.get("animal_type") == "Dog")
    cats = sum(1 for p in pets_list if p.get("animal_type") == "Cat")
    others = total - dogs - cats
    recent = pets_list[:6]

    # Optional recent activity feed.
    activity = []
    try:
        activity = list(db["activity"].find().sort("created_at", DESCENDING).limit(8))
    except PyMongoError:
        activity = []
    # Only surface activity types the dashboard renders.
    activity = [
        a for a in activity if a.get("action") in ("created", "updated", "deleted")
    ]

    stats = {
        "total": total,
        "dogs": dogs,
        "cats": cats,
        "others": others,
        "vaccinated": sum(1 for p in pets_list if p.get("vaccination_status") == "Vaccinated"),
    }

    return render_template(
        "dashboard.html",
        stats=stats,
        recent_pets=recent,
        activity=activity,
        page_title="Dashboard",
    )


# ---------------------------------------------------------------------------
# Pet records list
# ---------------------------------------------------------------------------


@app.route("/pets")
def pet_list():
    q = (request.args.get("q") or "").strip()
    animal = (request.args.get("animal") or "").strip()
    vacc = (request.args.get("vacc") or "").strip()
    sort = (request.args.get("sort") or "").strip()
    view = (request.args.get("view") or "").strip()

    # Fall back to the preferences saved on the Settings page.
    saved = load_settings()
    if sort not in ("newest", "oldest", "name_asc", "name_desc"):
        sort = saved.get("default_sort") or "newest"
    if view not in ("table", "cards"):
        view = saved.get("default_view") or "table"

    query: dict = {}
    if animal and animal in ANIMAL_TYPES:
        query["animal_type"] = animal
    if vacc and vacc in VACCINATION_OPTIONS:
        query["vaccination_status"] = vacc
    if q:
        # Case-insensitive partial match on the searchable fields.
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [
            {"pet_id": rx},
            {"pet_name": rx},
            {"breed": rx},
            {"owner_name": rx},
        ]

    sort_map = {
        "newest": [("created_at", DESCENDING), ("pet_id", DESCENDING)],
        "oldest": [("created_at", ASCENDING), ("pet_id", ASCENDING)],
        "name_asc": [("pet_name", ASCENDING)],
        "name_desc": [("pet_name", DESCENDING)],
    }
    order = sort_map.get(sort, sort_map["newest"])

    # ---- Pagination -----------------------------------------------------
    per_page = max(1, int(app.config.get("PER_PAGE", 10)))
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    page = max(1, page)

    try:
        total = pets.count_documents(query)
        total_pages = max(1, math.ceil(total / per_page)) if total else 1
        # Clamp so an out-of-range page never shows a broken empty screen.
        page = min(page, total_pages)

        cursor = (
            pets.find(query)
            .sort(order)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
        records = [serialize_pet(p) for p in cursor]
    except PyMongoError:
        total, records, total_pages, page = 0, [], 1, 1
        flash("Could not load pet records from MongoDB.", "error")

    # Only keep query params that actually narrow the results, so the
    # pagination links stay clean while preserving the user's filters.
    retained = {
        k: v
        for k, v in request.args.items()
        if k in ("q", "animal", "vacc", "sort", "view") and v
    }

    pagination = {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "retained": retained,
    }

    return render_template(
        "pets.html",
        records=records,
        total=total,
        q=q,
        animal=animal,
        vacc=vacc,
        sort=sort,
        view=view,
        pagination=pagination,
        page_title="Pet Records",
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@app.route("/pets/new")
@admin_required
def pet_new():
    form = request.args.to_dict() if request.method == "GET" else {}
    return render_template(
        "add_pet.html",
        form=form or {},
        errors={},
        page_title="Add New Pet",
    )


@app.route("/pets/create", methods=["POST"])
@admin_required
def pet_create():
    data, errors = validate_pet_form(request.form)

    photo_filename = None
    file = request.files.get("photo")
    max_bytes = app.config["MAX_CONTENT_LENGTH"]

    has_file = bool(file and file.filename)
    if has_file:
        ok, msg = validate_image_file(file, max_bytes)
        if not ok:
            errors["photo"] = msg

    if errors:
        flash_errors(errors)
        return render_template(
            "add_pet.html",
            form=request.form.to_dict(),
            errors=errors,
            page_title="Add New Pet",
        ), 400

    try:
        if has_file:
            photo_filename = save_upload(file)

        doc = {
            "pet_id": generate_pet_id(),
            "pet_name": data["pet_name"],
            "animal_type": data["animal_type"],
            "breed": data["breed"],
            "sex": data["sex"],
            "date_of_birth": data["date_of_birth"],
            "estimated_age": data["estimated_age"],
            "color": data["color"],
            "weight": data["weight"],
            "owner_name": data["owner_name"],
            "owner_contact": data["owner_contact"],
            "owner_email": data["owner_email"],
            "owner_address": data["owner_address"],
            "vaccination_status": data["vaccination_status"],
            "medical_notes": data["medical_notes"],
            "photo_filename": photo_filename,
            "registration_date": data["registration_date"] or today_str(),
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }

        result = pets.insert_one(doc)
        # Unique index may reject a duplicate pet_id; insert_one raises on that.
    except PyMongoError as exc:
        if has_file and photo_filename:
            delete_upload(photo_filename)
        app.logger.error("MongoDB insert failed: %s", exc)
        flash("Could not save the pet record to MongoDB. Please try again.", "error")
        return render_template(
            "add_pet.html",
            form=request.form.to_dict(),
            errors={},
            page_title="Add New Pet",
        ), 500

    add_activity("created", f"{doc['pet_name']} ({doc['pet_id']}) was registered.")
    flash(f"Pet record {doc['pet_id']} was created successfully.", "success")
    return redirect(url_for("pet_details", pet_id=doc["pet_id"]))


# ---------------------------------------------------------------------------
# Details
# ---------------------------------------------------------------------------


@app.route("/pets/<pet_id>")
def pet_details(pet_id: str):
    doc = pets.find_one({"pet_id": pet_id})
    if not doc:
        flash(f"No pet record found with id “{pet_id}”.", "error")
        return render_template(
            "404.html", context={"pet_id": pet_id}, page_title="Not Found"
        ), 404
    return render_template(
        "pet_details.html", pet=serialize_pet(doc), page_title=doc.get("pet_name", "Pet")
    )


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@app.route("/pets/<pet_id>/edit")
@admin_required
def pet_edit(pet_id: str):
    doc = pets.find_one({"pet_id": pet_id})
    if not doc:
        flash(f"No pet record found with id “{pet_id}”.", "error")
        return render_template(
            "404.html", context={"pet_id": pet_id}, page_title="Not Found"
        ), 404
    return render_template(
        "edit_pet.html",
        pet=serialize_pet(doc),
        form=serialize_pet(doc),
        errors={},
        page_title=f"Edit {doc.get('pet_name', 'Pet')}",
    )


@app.route("/pets/<pet_id>/update", methods=["POST"])
@admin_required
def pet_update(pet_id: str):
    doc = pets.find_one({"pet_id": pet_id})
    if not doc:
        flash(f"No pet record found with id “{pet_id}”.", "error")
        return render_template(
            "404.html", context={"pet_id": pet_id}, page_title="Not Found"
        ), 404

    data, errors = validate_pet_form(request.form, is_edit=True)

    file = request.files.get("photo")
    has_file = bool(file and file.filename)
    old_photo = doc.get("photo_filename")
    max_bytes = app.config["MAX_CONTENT_LENGTH"]
    new_photo = None

    if has_file:
        ok, msg = validate_image_file(file, max_bytes)
        if not ok:
            errors["photo"] = msg

    if errors:
        flash_errors(errors)
        return render_template(
            "edit_pet.html",
            pet=serialize_pet(doc),
            form=request.form.to_dict(),
            errors=errors,
            page_title=f"Edit {doc.get('pet_name', 'Pet')}",
        ), 400

    try:
        if has_file:
            # Save the new file first; only delete the old one after success.
            new_photo = save_upload(file)

        update_doc = {
            "pet_name": data["pet_name"],
            "animal_type": data["animal_type"],
            "breed": data["breed"],
            "sex": data["sex"],
            "date_of_birth": data["date_of_birth"],
            "estimated_age": data["estimated_age"],
            "color": data["color"],
            "weight": data["weight"],
            "owner_name": data["owner_name"],
            "owner_contact": data["owner_contact"],
            "owner_email": data["owner_email"],
            "owner_address": data["owner_address"],
            "vaccination_status": data["vaccination_status"],
            "medical_notes": data["medical_notes"],
            "photo_filename": new_photo or old_photo,
            "registration_date": data["registration_date"] or doc.get("registration_date"),
            "updated_at": now_iso(),
        }

        result = pets.update_one({"_id": doc["_id"]}, {"$set": update_doc})
        if result.matched_count == 0:
            raise PyMongoError("matched no document")

        # Delete the previous photo only after the replacement was stored.
        if new_photo and old_photo and old_photo != new_photo:
            delete_upload(old_photo)
    except PyMongoError as exc:
        if new_photo:
            delete_upload(new_photo)
        app.logger.error("MongoDB update failed: %s", exc)
        flash("Could not update the pet record. Please try again.", "error")
        return render_template(
            "edit_pet.html",
            pet=serialize_pet(doc),
            form=request.form.to_dict(),
            errors={},
            page_title=f"Edit {doc.get('pet_name', 'Pet')}",
        ), 500

    add_activity("updated", f"{data['pet_name']} ({pet_id}) was updated.")
    flash(f"Pet record {pet_id} was updated successfully.", "success")
    return redirect(url_for("pet_details", pet_id=pet_id))


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@app.route("/pets/<pet_id>/delete", methods=["POST"])
@admin_required
def pet_delete(pet_id: str):
    doc = pets.find_one({"pet_id": pet_id})
    if not doc:
        flash(f"No pet record found with id “{pet_id}”.", "error")
        return redirect(url_for("pet_list"))

    try:
        # Belt and braces: refuse any GET/HEAD request.
        if request.method != "POST":
            raise RuntimeError("Deletes must use POST.")

        result = pets.delete_one({"_id": doc["_id"]})
        if result.deleted_count == 0:
            raise PyMongoError("nothing deleted")
    except PyMongoError as exc:
        app.logger.error("MongoDB delete failed: %s", exc)
        flash("Could not delete the pet record. Please try again.", "error")
        return redirect(url_for("pet_details", pet_id=pet_id))

    # Remove the photo only after the database row is gone.
    delete_upload(doc.get("photo_filename"))

    add_activity("deleted", f"{doc.get('pet_name', 'Pet')} ({pet_id}) was removed.")
    flash(f"Pet record {pet_id} was deleted.", "success")
    return redirect(url_for("pet_list"))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def load_settings() -> dict:
    doc = settings_col.find_one({"_id": "app_settings"})
    if doc:
        return doc
    return {
        "_id": "app_settings",
        "theme": "system",
        "default_sort": "newest",
        "default_view": "table",
        "profile_display_name": "",
        "profile_email": "",
        "updated_at": None,
    }


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        form = request.form
        doc = {
            "theme": form.get("theme", "system"),
            "default_sort": form.get("default_sort", "newest"),
            "default_view": form.get("default_view", "table"),
            "profile_display_name": (form.get("profile_display_name") or "").strip()[:80],
            "profile_email": (form.get("profile_email") or "").strip()[:120],
            "updated_at": now_iso(),
        }
        if doc["theme"] not in ("light", "dark", "system"):
            doc["theme"] = "system"
        if doc["default_sort"] not in ("newest", "oldest", "name_asc", "name_desc"):
            doc["default_sort"] = "newest"
        if doc["default_view"] not in ("table", "cards"):
            doc["default_view"] = "table"
        if doc["profile_email"] and not EMAIL_RE.match(doc["profile_email"]):
            flash("Please enter a valid e-mail address in your profile.", "error")
            return render_template(
                "settings.html",
                settings=load_settings(),
                page_title="Settings",
                form=form.to_dict(),
            ), 400

        try:
            settings_col.update_one(
                {"_id": "app_settings"}, {"$set": doc}, upsert=True
            )
        except PyMongoError:
            flash("Could not save settings to MongoDB.", "error")
            return render_template(
                "settings.html",
                settings=load_settings(),
                page_title="Settings",
                form=form.to_dict(),
            ), 500

        flash("Settings saved.", "success")
        return redirect(url_for("settings"))

    return render_template(
        "settings.html", settings=load_settings(), page_title="Settings", form={}
    )


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html", page_title="Page Not Found"), 404


@app.errorhandler(403)
def forbidden(_e):
    """Signed-in user without the required role."""
    return render_template(
        "403.html",
        required_roles=("Administrator",),
        page_title="Access Denied",
    ), 403


@app.errorhandler(500)
def server_error(_e):
    return render_template("500.html", page_title="Server Error"), 500


@app.errorhandler(RequestEntityTooLarge)
def too_large(_e):
    """Handle uploads bigger than MAX_CONTENT_LENGTH.

    Important: never touch `request.form` / `request.files` here — doing so
    would try to parse the oversized body and re-raise the same exception.
    """
    mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    flash(
        f"The uploaded file is too large. Maximum allowed size is {mb} MB. "
        "Please try again with a smaller photo.",
        "error",
    )
    if request.endpoint == "pet_create":
        # Can't render the form (the body was never parsed), so send the user
        # back to a fresh, empty form with the error already flashed.
        return redirect(url_for("pet_new")), 413
    if request.endpoint == "pet_update":
        return redirect(request.referrer or url_for("pet_list")), 413
    return redirect(url_for("dashboard")), 413


@app.errorhandler(CSRFError)
def csrf_error(_e):
    flash("Your session expired. Please try again.", "error")
    return redirect(request.referrer or url_for("dashboard"))


def _port_in_use(host: str, port: int) -> bool:
    """Return True if something is already listening on `host:port`.

    On Windows two processes *can* bind the same port, which makes requests
    get answered nondeterministically by old and new code. Catching it here
    gives a clear message instead of mysterious 500s later.
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = int(os.environ.get("PORT", "5000"))

    if _port_in_use(HOST, PORT):
        raise SystemExit(
            f"\nERROR: Port {PORT} is already in use.\n"
            f"Another instance of PetCare (or another program) is running "
            f"there.\n"
            f"Stop it first, then start the app again:\n"
            f"  * If you have a terminal running it: press CTRL+C there.\n"
            f"  * Otherwise find and stop the process, e.g.:\n"
            f"      netstat -ano | findstr :{PORT}\n"
            f"      taskkill /F /PID <pid shown above>\n"
            f"  * Or run this instance on another port:\n"
            f"      PORT={PORT + 1} python app.py\n"
        )

    # `use_reloader=False` keeps a single process, which is fine for this app.
    app.run(
        host=HOST,
        port=PORT,
        debug=app.config["DEBUG"],
        use_reloader=False,
    )