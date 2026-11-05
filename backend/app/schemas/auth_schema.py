import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,24}$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9\-\s]{6,20}$")
_HTML_TAG_RE = re.compile(r"[<>]")


def validate_clean_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if not email or len(email) > 254 or not _EMAIL_RE.match(email):
        raise ValueError("Enter a valid email address (e.g., client@noiratelier.in).")
    return email


def validate_clean_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", (raw or "").strip())
    if len(name) < 2 or len(name) > 120:
        raise ValueError("Full name must be between 2 and 120 characters.")
    if _HTML_TAG_RE.search(name):
        raise ValueError("Name contains disallowed characters.")
    return name


def validate_clean_phone(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    if not _PHONE_RE.match(cleaned):
        raise ValueError("Phone number must be 7–21 digits (optional '+' and hyphens).")
    return cleaned


def validate_password_strength(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if len(password) > 128:
        raise ValueError("Password must not exceed 128 characters.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must include at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must include at least one lowercase letter.")
    if not re.search(r"[0-9]", password):
        raise ValueError("Password must include at least one number.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must include at least one special character (e.g., !@#$%).")
    return password


class CustomerRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)
    phone: Optional[str] = Field(default=None, max_length=32)
    preferred_department: Optional[str] = Field(default=None, max_length=16)

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        return validate_clean_name(v)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return validate_clean_email(v)

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: Optional[str]) -> Optional[str]:
        return validate_clean_phone(v)


class AdminRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)
    role_code: str = Field(default="manager", min_length=3, max_length=32)
    phone: Optional[str] = Field(default=None, max_length=32)
    department_scope: Optional[str] = Field(default=None, max_length=16)
    invite_code: Optional[str] = Field(default=None, max_length=128)

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        return validate_clean_name(v)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return validate_clean_email(v)

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("role_code")
    @classmethod
    def _check_role(cls, v: str) -> str:
        return (v or "").strip().lower()

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: Optional[str]) -> Optional[str]:
        return validate_clean_phone(v)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)
    portal: str = Field(default="auto")

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return validate_clean_email(v)

    @field_validator("portal")
    @classmethod
    def _check_portal(cls, v: str) -> str:
        cleaned = (v or "auto").strip().lower()
        if cleaned not in ("auto", "customer", "admin"):
            raise ValueError("Portal must be 'auto', 'customer', or 'admin'.")
        return cleaned


class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = None


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _check_new_password(cls, v: str) -> str:
        return validate_password_strength(v)


class StaffCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)
    role_code: str = Field(..., min_length=3, max_length=32)
    phone: Optional[str] = Field(default=None, max_length=32)
    department_scope: Optional[str] = Field(default=None, max_length=16)

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        return validate_clean_name(v)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return validate_clean_email(v)

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("role_code")
    @classmethod
    def _check_role(cls, v: str) -> str:
        return (v or "").strip().lower()

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, v: Optional[str]) -> Optional[str]:
        return validate_clean_phone(v)


class StaffUpdateRequest(BaseModel):
    role_code: Optional[str] = Field(default=None, min_length=3, max_length=32)
    status: Optional[str] = Field(default=None)
    department_scope: Optional[str] = Field(default=None, max_length=16)
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)

    @field_validator("role_code")
    @classmethod
    def _check_role(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if v is not None else None

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().lower()
        if cleaned not in ("active", "suspended"):
            raise ValueError("Status must be 'active' or 'suspended'.")
        return cleaned

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: Optional[str]) -> Optional[str]:
        return validate_clean_name(v) if v is not None else None


class CustomerStatusUpdateRequest(BaseModel):
    status: Optional[str] = Field(default=None)
    loyalty_tier: Optional[str] = Field(default=None)

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().lower()
        if cleaned not in ("active", "suspended"):
            raise ValueError("Status must be 'active' or 'suspended'.")
        return cleaned

    @field_validator("loyalty_tier")
    @classmethod
    def _check_tier(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().upper()
        if cleaned not in ("STANDARD", "VIP_GOLD", "PRIVATE_CLIENT"):
            raise ValueError("Loyalty tier must be 'STANDARD', 'VIP_GOLD', or 'PRIVATE_CLIENT'.")
        return cleaned
