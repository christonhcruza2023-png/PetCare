"""Central configuration for the PetCare application.

Every value here can be overridden through environment variables or the
`.env` file in the project root. See `.env.example`.
"""

from __future__ import annotations

import os
from datetime import timedelta

from dotenv import load_dotenv

# Load `.env` (if present) before reading values.
load_dotenv()


BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration shared by every environment."""

    # --- General ---------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"

    # --- MongoDB ---------------------------------------------------
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "petcare_db")
    MONGO_COLLECTION = os.environ.get("MONGO_COLLECTION", "pets")
    # Extra collection used for the Settings page / recent activity.
    MONGO_SETTINGS_COLLECTION = "settings"

    # --- Uploads ---------------------------------------------------
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "5")) * 1024 * 1024
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # --- Roles -----------------------------------------------------
    # Optional bootstrap administrator. If both are set and the users
    # collection is empty, this account is created on start-up.
    # When they are NOT set, the very first account registered becomes
    # the administrator automatically.
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "").strip()
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

    # --- Sessions --------------------------------------------------
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # --- Pagination ------------------------------------------------
    PER_PAGE = 10