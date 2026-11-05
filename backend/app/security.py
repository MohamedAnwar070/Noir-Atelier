from collections import deque
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import threading
import time
from typing import Any, Deque, Dict, Optional, Tuple
import uuid

from fastapi import Request, Response
import jwt

from .config import get_settings
from .utils.exceptions import AppError

try:
    from argon2 import PasswordHasher as Argon2PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

    _ARGON2_HASHER: Optional[Any] = Argon2PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=2,
        hash_len=32,
        salt_len=16,
    )
except ImportError:  # pragma: no cover - fallback when argon2-cffi is unavailable
    _ARGON2_HASHER = None
    InvalidHashError = ValueError  # type: ignore[misc,assignment]
    VerificationError = ValueError  # type: ignore[misc,assignment]
    VerifyMismatchError = ValueError  # type: ignore[misc,assignment]


ACCESS_COOKIE_NAME = "noir_access_token"
REFRESH_COOKIE_NAME = "noir_refresh_token"
JWT_ISSUER = "noir-atelier"

_SCRYPT_N = 16384
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


def _scrypt_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"$scrypt$n={_SCRYPT_N},r={_SCRYPT_R},p={_SCRYPT_P}${salt.hex()}${derived.hex()}"


def _scrypt_verify(password: str, encoded: str) -> bool:
    try:
        parts = encoded.split("$")
        if len(parts) != 5 or parts[1] != "scrypt":
            return False
        params = dict(kv.split("=", 1) for kv in parts[2].split(","))
        salt = bytes.fromhex(parts[3])
        expected = bytes.fromhex(parts[4])
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(params["n"]),
            r=int(params["r"]),
            p=int(params["p"]),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def hash_password(password: str) -> str:
    settings = get_settings()
    if _ARGON2_HASHER is not None and settings.password_hasher.lower() == "argon2":
        return str(_ARGON2_HASHER.hash(password))
    return _scrypt_hash(password)


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith("$argon2") and _ARGON2_HASHER is not None:
        try:
            return bool(_ARGON2_HASHER.verify(password_hash, password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    if password_hash.startswith("$scrypt$"):
        return _scrypt_verify(password, password_hash)
    return False


def password_needs_rehash(password_hash: Optional[str]) -> bool:
    if not password_hash:
        return True
    settings = get_settings()
    if _ARGON2_HASHER is not None and settings.password_hasher.lower() == "argon2":
        if not password_hash.startswith("$argon2"):
            return True
        return bool(_ARGON2_HASHER.check_needs_rehash(password_hash))
    return False


_DUMMY_PASSWORD_HASH: Optional[str] = None
_DUMMY_LOCK = threading.Lock()


def verify_password_constant_time(password: str, password_hash: Optional[str]) -> bool:
    """Verify password while mitigating timing-based account enumeration."""
    global _DUMMY_PASSWORD_HASH
    if not password_hash:
        with _DUMMY_LOCK:
            if _DUMMY_PASSWORD_HASH is None:
                _DUMMY_PASSWORD_HASH = hash_password("NoirAtelier#DummyTimingGuard2026!")
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return False
    return verify_password(password, password_hash)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _derive_signing_key(raw_secret: str, purpose: str) -> bytes:
    """Derive a 256-bit domain-separated HMAC signing key compliant with RFC 7518 §3.2."""
    if len(raw_secret.encode("utf-8")) >= 32 and purpose == "raw":
        return raw_secret.encode("utf-8")
    return hmac.new(
        key=f"noir-atelier-jwt-{purpose}".encode("utf-8"),
        msg=raw_secret.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()


def constant_time_equals(a: Optional[str], b: Optional[str]) -> bool:
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def create_access_token_bundle(
    actor_id: str,
    actor_type: str = "customer",
    role: str = "customer",
    email: Optional[str] = None,
    name: Optional[str] = None,
    session_id: Optional[str] = None,
    on_behalf_of: Optional[str] = None,
    ttl_minutes: Optional[int] = None,
) -> Tuple[str, str, int]:
    settings = get_settings()
    exp_min = ttl_minutes or settings.access_token_ttl_min
    now = datetime.now(timezone.utc)
    exp_dt = now + timedelta(minutes=exp_min)
    jti = str(uuid.uuid4())
    payload: Dict[str, Any] = {
        "sub": actor_id,
        "actor_type": actor_type,
        "role": role,
        "typ": "access",
        "jti": jti,
        "iss": JWT_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int(exp_dt.timestamp()),
    }
    if email:
        payload["email"] = email
    if name:
        payload["name"] = name
    if session_id:
        payload["sid"] = session_id
    if on_behalf_of:
        payload["on_behalf_of"] = on_behalf_of
    token = jwt.encode(
        payload,
        _derive_signing_key(settings.jwt_secret, "access"),
        algorithm=settings.jwt_algorithm,
    )
    return token, jti, int(exp_min * 60)


def create_refresh_token_bundle(
    actor_id: str,
    actor_type: str,
    role: str,
    session_id: str,
    token_family: str,
    ttl_days: Optional[int] = None,
) -> Tuple[str, datetime]:
    settings = get_settings()
    exp_days = ttl_days or settings.refresh_token_ttl_days
    now = datetime.now(timezone.utc)
    exp_dt = now + timedelta(days=exp_days)
    payload: Dict[str, Any] = {
        "sub": actor_id,
        "actor_type": actor_type,
        "role": role,
        "sid": session_id,
        "fam": token_family,
        "jti": str(uuid.uuid4()),
        "typ": "refresh",
        "iss": JWT_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int(exp_dt.timestamp()),
    }
    token = jwt.encode(
        payload,
        _derive_signing_key(settings.jwt_refresh_secret, "refresh"),
        algorithm=settings.jwt_algorithm,
    )
    return token, exp_dt


def decode_access_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            _derive_signing_key(settings.jwt_secret, "access"),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError("token_expired", "Access token has expired. Please refresh your session.", 401) from exc
    except jwt.PyJWTError as exc:
        raise AppError("invalid_token", f"Invalid authentication token: {exc}", 401) from exc

    tok_type = payload.get("typ", "access")
    if tok_type != "access":
        raise AppError("invalid_token_type", "Refresh tokens cannot be used as access tokens.", 401)
    return payload


def decode_refresh_token(token: str) -> Dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            _derive_signing_key(settings.jwt_refresh_secret, "refresh"),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "sid", "fam", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError("refresh_token_expired", "Session has expired. Please sign in again.", 401) from exc
    except jwt.PyJWTError as exc:
        raise AppError("invalid_refresh_token", "Invalid session refresh token.", 401) from exc

    if payload.get("typ") != "refresh":
        raise AppError("invalid_token_type", "Expected a valid refresh token.", 401)
    return payload


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
    access_max_age_sec: int,
    refresh_max_age_sec: int,
) -> None:
    settings = get_settings()
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        max_age=access_max_age_sec,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=refresh_max_age_sec,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/auth",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key=ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/api/auth")


def extract_client_meta(request: Request) -> Tuple[Optional[str], Optional[str]]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",")[0].strip()[:64]
    elif request.client and request.client.host:
        ip = str(request.client.host)[:64]
    else:
        ip = None
    ua = request.headers.get("user-agent")
    return ip, (ua.strip()[:255] if ua else None)


class AuthRateLimiter:
    """Thread-safe sliding-window rate limiter for authentication endpoints."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: Dict[str, Deque[float]] = {}

    def check(self, key: str, limit: Optional[int] = None, window_seconds: int = 60) -> None:
        max_hits = limit if limit is not None else get_settings().auth_rate_limit_per_min
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = deque()
                self._buckets[key] = bucket
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= max_hits:
                raise AppError(
                    code="rate_limit_exceeded",
                    message="Too many authentication attempts. Please wait a moment and try again.",
                    status_code=429,
                    details={"retry_after_seconds": window_seconds},
                )
            bucket.append(now)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


auth_rate_limiter = AuthRateLimiter()
