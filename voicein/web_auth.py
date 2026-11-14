"""Password hashing and signed session cookies for the phone web UI."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from voicein.config import config_dir

_PBKDF2_ROUNDS = 210_000
_MIN_PASSWORD_LEN = 12
_COOKIE_NAME = "voicein_auth"


@dataclass
class WebAuth:
    password_salt: bytes
    password_hash: bytes
    session_secret: bytes
    session_days: int = 90


def auth_path() -> Path:
    return config_dir() / "web-auth.toml"


def generate_password() -> str:
    """Readable 20-char password (hex groups) — store in a password manager, not a 4-digit PIN."""
    raw = secrets.token_hex(10)
    return f"{raw[0:5]}-{raw[5:10]}-{raw[10:15]}-{raw[15:20]}"


def hash_password(password: str, *, salt: bytes | None = None) -> tuple[bytes, bytes]:
    if salt is None:
        salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return salt, dk


def verify_password(auth: WebAuth, password: str) -> bool:
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        auth.password_salt,
        _PBKDF2_ROUNDS,
    )
    return hmac.compare_digest(dk, auth.password_hash)


def validate_new_password(password: str) -> str | None:
    stripped = password.strip()
    if len(stripped) < _MIN_PASSWORD_LEN:
        return f"Password must be at least {_MIN_PASSWORD_LEN} characters (short PINs are not safe on the public internet)."
    if stripped.isdigit() and len(stripped) < 16:
        return "Numeric-only secrets must be at least 16 digits. Prefer the generated password."
    return None


def write_auth(auth: WebAuth) -> None:
    path = auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f'password_salt = "{auth.password_salt.hex()}"\n'
        f'password_hash = "{auth.password_hash.hex()}"\n'
        f'session_secret = "{auth.session_secret.hex()}"\n'
        f"session_days = {int(auth.session_days)}\n"
    )
    path.write_text(body, encoding="utf-8")
    os.chmod(path, 0o600)


def load_auth() -> WebAuth | None:
    path = auth_path()
    if not path.is_file():
        return None
    import tomllib

    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    try:
        return WebAuth(
            password_salt=bytes.fromhex(str(raw["password_salt"])),
            password_hash=bytes.fromhex(str(raw["password_hash"])),
            session_secret=bytes.fromhex(str(raw["session_secret"])),
            session_days=int(raw.get("session_days", 90)),
        )
    except (KeyError, ValueError):
        return None


def issue_cookie(auth: WebAuth) -> str:
    expiry = int(time.time()) + auth.session_days * 86400
    nonce = secrets.token_hex(16)
    payload = f"{expiry}.{nonce}"
    mac = hmac.new(auth.session_secret, payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{mac}"


def cookie_valid(auth: WebAuth, token: str | None) -> bool:
    if not token:
        return False
    parts = token.split(".")
    if len(parts) != 3:
        return False
    expiry_s, nonce, mac = parts
    if not expiry_s.isdigit() or not nonce:
        return False
    payload = f"{expiry_s}.{nonce}"
    expected = hmac.new(auth.session_secret, payload.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        return False
    return int(expiry_s) >= int(time.time())


def cookie_header(token: str, *, max_age: int, secure: bool) -> str:
    bits = [
        f"{_COOKIE_NAME}={token}",
        "HttpOnly",
        "Path=/",
        "SameSite=Strict",
        f"Max-Age={max_age}",
    ]
    if secure:
        bits.append("Secure")
    return "; ".join(bits)


def clear_cookie_header(*, secure: bool) -> str:
    bits = [
        f"{_COOKIE_NAME}=",
        "HttpOnly",
        "Path=/",
        "SameSite=Strict",
        "Max-Age=0",
    ]
    if secure:
        bits.append("Secure")
    return "; ".join(bits)


def parse_cookie_header(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == _COOKIE_NAME:
            return value.strip() or None
    return None
