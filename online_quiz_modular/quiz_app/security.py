"""Password hashing, input validation and login throttling (no Streamlit).

Hash format
-----------
New passwords are stored as ``pbkdf2$<salt-hex>$<hash-hex>`` (PBKDF2-HMAC-SHA256,
200 000 iterations).  Very old databases may still hold plain SHA-256 hex
digests; those are still accepted and are upgraded the next time the user
signs in (see ``auth.authenticate``).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading
import time
from typing import Dict, Optional

from . import config

# NOTE: must stay 200000 - existing stored hashes do not record the iteration
# count, so changing it would lock every existing user out.
HASH_ITERATIONS = 200_000


# --------------------------------------------------------------------------
# Password hashing
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Return a salted PBKDF2 hash string for ``password``."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, HASH_ITERATIONS
    ).hex()
    return f"pbkdf2${salt.hex()}${digest}"


def is_legacy_hash(stored: Optional[str]) -> bool:
    """True when ``stored`` is an old unsalted SHA-256 digest."""
    return bool(stored) and not str(stored).startswith("pbkdf2$")


def verify_password(password: str, stored: Optional[str]) -> bool:
    """Check ``password`` against a stored hash (new or legacy format)."""
    if not stored:
        return False
    try:
        if stored.startswith("pbkdf2$"):
            _, salt, old_hash = stored.split("$")
            new_hash = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt), HASH_ITERATIONS
            ).hex()
            return hmac.compare_digest(new_hash, old_hash)

        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy, stored)
    except (ValueError, AttributeError, TypeError):
        return False


# --------------------------------------------------------------------------
# Validation (each returns an error message, or None when the value is fine)
# --------------------------------------------------------------------------
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,30}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_username(username: str) -> Optional[str]:
    username = (username or "").strip()
    if not username:
        return "Please choose a username."
    if not _USERNAME_RE.match(username):
        return "Username must be 3-30 characters: letters, numbers, dot, dash or underscore."
    return None


def validate_full_name(name: str) -> Optional[str]:
    name = (name or "").strip()
    if not name:
        return "Please enter your full name (it is printed on your certificate)."
    if len(name) > 60:
        return "Full name must be 60 characters or fewer."
    return None


def validate_email(email: str) -> Optional[str]:
    email = (email or "").strip()
    if email and not _EMAIL_RE.match(email):
        return "Please enter a valid e-mail address or leave it empty."
    return None


def validate_password(password: str, confirm: Optional[str] = None) -> Optional[str]:
    if not password:
        return "Please enter a password."
    if len(password) < config.MIN_PASSWORD_LENGTH:
        return f"Password must have at least {config.MIN_PASSWORD_LENGTH} characters."
    if confirm is not None and password != confirm:
        return "Passwords do not match."
    return None


# --------------------------------------------------------------------------
# Login throttling
# --------------------------------------------------------------------------
class LoginThrottle:
    """Temporarily locks a login name after too many failed attempts.

    The instance lives at module level, so it is shared by every browser
    session of the running Streamlit process.  It is thread-safe.
    """

    def __init__(self, max_attempts: int, lockout_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self._failures: Dict[str, list] = {}   # key -> [count, locked_until]
        self._lock = threading.Lock()

    def seconds_locked(self, key: str) -> int:
        """Seconds left on the lock for ``key`` (0 when not locked)."""
        with self._lock:
            entry = self._failures.get(key)
            if not entry:
                return 0
            remaining = int(entry[1] - time.time())
            if remaining <= 0 and entry[1]:
                self._failures.pop(key, None)
                return 0
            return max(0, remaining)

    def register_failure(self, key: str) -> None:
        with self._lock:
            entry = self._failures.setdefault(key, [0, 0.0])
            entry[0] += 1
            if entry[0] >= self.max_attempts:
                entry[1] = time.time() + self.lockout_seconds
                entry[0] = 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


THROTTLE = LoginThrottle(config.MAX_FAILED_LOGINS, config.LOCKOUT_SECONDS)
