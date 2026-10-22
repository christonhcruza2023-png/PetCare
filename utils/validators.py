"""Server-side validation helpers used by the Flask routes.

All user input passes through `validate_pet_form` before it reaches MongoDB.
File uploads pass through `validate_image_file`, which checks that the file is
actually an image (magic bytes), has an allowed extension, and fits inside the
size limit.
"""

from __future__ import annotations

import os
import re
from datetime import date

# ---------------------------------------------------------------------------
# Allowed values / look-ups
# ---------------------------------------------------------------------------

ANIMAL_TYPES = [
    "Dog",
    "Cat",
    "Bird",
    "Rabbit",
    "Fish",
    "Reptile",
    "Other",
]

SEX_OPTIONS = ["Male", "Female"]

VACCINATION_OPTIONS = [
    "Vaccinated",
    "Partially Vaccinated",
    "Not Vaccinated",
]

# Fields a user is always required to fill in.
REQUIRED_FIELDS = ["pet_name", "animal_type", "owner_name"]

# Simple phone / contact pattern: digits, spaces, +, -, ()
PHONE_RE = re.compile(r"^[0-9+\-\s()]{6,20}$")

# Rough email pattern (email-validator is imported lazily when available).
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


# ---------------------------------------------------------------------------
# Whole-form validation
# ---------------------------------------------------------------------------

def validate_pet_form(form, is_edit: bool = False) -> dict:
    """Validate a submitted pet form.

    Returns a tuple ``(clean_data, errors)``. `clean_data` only contains
    recognised keys, with whitespace already stripped. `errors` is a dict of
    ``field_name -> message`` (empty dict means the form is valid).
    """
    data: dict = {}
    errors: dict = {}

    def text(key: str, max_len: int = 500, required: bool = False, label: str = "") -> str:
        value = (form.get(key) or "").strip()
        label = label or key.replace("_", " ").title()
        if required and not value:
            errors[key] = f"{label} is required."
            return ""
        if value and len(value) > max_len:
            errors[key] = f"{label} must be {max_len} characters or fewer."
            return value[:max_len]
        return value

    # --- Simple text fields ---------------------------------------
    data["pet_name"] = text("pet_name", 80, required=True, label="Pet Name")
    data["breed"] = text("breed", 80)
    data["color"] = text("color", 60)
    data["estimated_age"] = text("estimated_age", 40)
    data["owner_name"] = text("owner_name", 120, required=True, label="Owner Name")
    data["owner_contact"] = text("owner_contact", 30)
    data["owner_email"] = text("owner_email", 120)
    data["owner_address"] = text("owner_address", 250)
    data["medical_notes"] = text("medical_notes", 1000)

    # --- Select fields --------------------------------------------
    animal_type = (form.get("animal_type") or "").strip()
    if not animal_type:
        errors["animal_type"] = "Animal type is required."
    elif animal_type not in ANIMAL_TYPES:
        errors["animal_type"] = "Please choose a valid animal type."
    data["animal_type"] = animal_type

    sex = (form.get("sex") or "").strip()
    if sex and sex not in SEX_OPTIONS:
        errors["sex"] = "Please choose a valid sex."
    data["sex"] = sex

    vaccination = (form.get("vaccination_status") or "").strip()
    if vaccination and vaccination not in VACCINATION_OPTIONS:
        errors["vaccination_status"] = "Please choose a valid vaccination status."
    data["vaccination_status"] = vaccination

    # --- Weight ----------------------------------------------------
    weight_raw = (form.get("weight") or "").strip()
    weight = None
    if weight_raw:
        try:
            weight = float(weight_raw)
            if weight <= 0 or weight > 1000:
                errors["weight"] = "Weight must be between 0 and 1000 kg."
        except ValueError:
            errors["weight"] = "Weight must be a number (kilograms)."
    data["weight"] = weight

    # --- Date of birth --------------------------------------------
    dob_raw = (form.get("date_of_birth") or "").strip()
    dob = None
    if dob_raw:
        try:
            dob = date.fromisoformat(dob_raw)
            if dob > date.today():
                errors["date_of_birth"] = "Date of birth cannot be in the future."
        except ValueError:
            errors["date_of_birth"] = "Date of birth must be a valid date (YYYY-MM-DD)."
    data["date_of_birth"] = dob_raw or None

    # DOB and estimated age are mutually exclusive options.
    if dob and data["estimated_age"]:
        errors["estimated_age"] = (
            "Provide either a date of birth or an estimated age, not both."
        )

    # --- Registration date ----------------------------------------
    reg_raw = (form.get("registration_date") or "").strip()
    if not reg_raw:
        reg_raw = date.today().isoformat()
    try:
        reg = date.fromisoformat(reg_raw)
        data["registration_date"] = reg_raw
    except ValueError:
        errors["registration_date"] = "Registration date must be a valid date (YYYY-MM-DD)."
        data["registration_date"] = reg_raw

    # --- Owner e-mail ---------------------------------------------
    email = data["owner_email"]
    if email:
        if not EMAIL_RE.match(email):
            errors["owner_email"] = "Please enter a valid e-mail address."
        else:
            try:  # optional stricter check when `email-validator` is installed
                import email_validator

                email_validator.validate_email(
                    email, check_deliverability=False
                )
            except ImportError:
                pass
            except email_validator.EmailNotValidError as exc:  # type: ignore[attr-defined]
                errors["owner_email"] = str(exc)

    if data["owner_contact"] and not PHONE_RE.match(data["owner_contact"]):
        errors["owner_contact"] = (
            "Contact number may only contain digits, spaces, +, - and ()."
        )

    if is_edit and not data["pet_name"]:
        # Already reported above; nothing extra to do.
        pass

    return data, errors


# ---------------------------------------------------------------------------
# Account (authentication) validation
# ---------------------------------------------------------------------------

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
MIN_PASSWORD_LEN = 6


def validate_registration(form) -> tuple[dict, dict]:
    """Validate the sign-up form. Returns ``(clean_data, errors)``."""
    data = {
        "username": (form.get("username") or "").strip(),
        "email": (form.get("email") or "").strip(),
        "password": form.get("password") or "",
        "confirm": form.get("confirm") or "",
    }
    errors: dict = {}

    if not data["username"]:
        errors["username"] = "Username is required."
    elif not USERNAME_RE.match(data["username"]):
        errors["username"] = (
            "Username must be 3–30 characters and may only contain letters, "
            "numbers and underscores."
        )

    if data["email"] and not EMAIL_RE.match(data["email"]):
        errors["email"] = "Please enter a valid e-mail address."

    if not data["password"]:
        errors["password"] = "Password is required."
    elif len(data["password"]) < MIN_PASSWORD_LEN:
        errors["password"] = (
            f"Password must be at least {MIN_PASSWORD_LEN} characters long."
        )

    if data["confirm"] != data["password"]:
        errors["confirm"] = "Passwords do not match."

    return data, errors


def validate_login(form) -> tuple[dict, dict]:
    """Validate the sign-in form. Returns ``(clean_data, errors)``."""
    data = {
        "username": (form.get("username") or "").strip(),
        "password": form.get("password") or "",
    }
    errors: dict = {}

    if not data["username"]:
        errors["username"] = "Username is required."
    if not data["password"]:
        errors["password"] = "Password is required."

    return data, errors


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------

# Bytes that start every allowed image format.
_MAGIC_SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"RIFF", "webp"),  # refined below
]

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def extension_of(filename: str) -> str:
    """Return the lower-cased extension without the dot."""
    return os.path.splitext(filename)[1].lstrip(".").lower()


def _looks_like_image(head: bytes, ext: str) -> bool:
    """Verify the leading bytes of an uploaded file match a real image."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ext == "png"
    if head.startswith(b"\xff\xd8\xff"):
        return ext in {"jpg", "jpeg"}
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ext == "webp"
    # GIF is explicitly NOT allowed (could be animated / abused).
    return False


def validate_image_file(file_storage, max_bytes: int) -> tuple[bool, str]:
    """Validate an uploaded pet photo.

    Returns ``(ok, message)``. The file stream is rewound on success so the
    caller can save it immediately afterwards.
    """
    if file_storage is None or not getattr(file_storage, "filename", ""):
        return False, "No file selected."

    filename = file_storage.filename
    ext = extension_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        return False, "Only JPG, JPEG, PNG and WEBP images are allowed."

    # Read the first bytes to make sure it really is an image.
    try:
        head = file_storage.stream.read(16)
        file_storage.stream.seek(0)
    except Exception:  # pragma: no cover - defensive
        return False, "Could not read the uploaded file."

    if not head:
        return False, "The uploaded file is empty."

    if not _looks_like_image(head, ext):
        return False, "The file content does not match an allowed image format."

    # Size check (Flask also enforces MAX_CONTENT_LENGTH globally).
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size == 0:
        return False, "The uploaded file is empty."
    if size > max_bytes:
        mb = max_bytes // (1024 * 1024)
        return False, f"Image is too large. Maximum allowed size is {mb} MB."

    return True, ""