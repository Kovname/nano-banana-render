"""
Credential persistence for Nano Banana Render addon.

Handles saving, loading, and deleting user credentials
(API key, email, name) to a persistent file on disk.
"""

import os
import json
import tempfile
import logging

import bpy

logger = logging.getLogger("nano_banana")


def get_credentials_path() -> str:
    """Get path to persistent credentials file."""
    cred_dir = os.path.join(tempfile.gettempdir(), "nanode_blender")
    os.makedirs(cred_dir, exist_ok=True)
    return os.path.join(cred_dir, "credentials.json")


def save_credentials_file(api_key: str, email: str, name: str) -> None:
    """Save credentials to a persistent file."""
    try:
        data = {"api_key": api_key, "email": email, "name": name}
        with open(get_credentials_path(), "w", encoding="utf-8") as f:
            json.dump(data, f)
        logger.info("Credentials saved to %s", get_credentials_path())
    except OSError as e:
        logger.error("Failed to save credentials: %s", e)


def load_credentials_file() -> dict:
    """Load credentials from persistent file. Returns {} if not found."""
    try:
        path = get_credentials_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to load credentials: %s", e)
    return {}


def delete_credentials_file() -> None:
    """Delete the persistent credentials file."""
    try:
        path = get_credentials_path()
        if os.path.exists(path):
            os.remove(path)
            logger.info("Credentials file deleted")
    except OSError as e:
        logger.error("Failed to delete credentials: %s", e)


def get_user_email() -> str:
    """Get the stored user email from credentials file."""
    return load_credentials_file().get("email", "")


def get_user_name() -> str:
    """Get the stored user name from credentials file."""
    return load_credentials_file().get("name", "")


def restore_credentials_on_startup() -> None:
    """Called on addon startup to restore credentials from file."""
    data = load_credentials_file()
    if data.get("api_key"):
        try:
            prefs = bpy.context.preferences.addons.get("nano_banana_render")
            if prefs and hasattr(prefs.preferences, "beta_token"):
                current = prefs.preferences.beta_token.strip()
                if not current:
                    prefs.preferences.beta_token = data["api_key"]
                    logger.info(
                        "Credentials restored for %s", data.get("email", "?")
                    )
        except Exception as e:
            logger.warning("Could not restore credentials: %s", e)
