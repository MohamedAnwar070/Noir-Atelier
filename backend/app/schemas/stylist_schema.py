"""Contract for the conversational stylist's living style profile.

One definition shared by the API (validates and stores it) and the stylist
agent (builds and updates it), so the two can never drift.

Privacy by construction: preferences only. No names, contact details, ID or
payment numbers — free-text fields are short, and anything that looks like a
long number is rejected.
"""

import re
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

PROFILE_SCHEMA_VERSION = 1

# Attribute fields validated against the live catalogue (GET /api/catalog/attributes).
CATALOG_FIELDS = ("department", "product_types", "colors", "palettes", "materials", "sizes", "occasion")

_LONG_NUMBER = re.compile(r"\d{5,}")


class AvoidList(BaseModel):
    """Things the shopper ruled out ("too bright", "no wool")."""

    model_config = ConfigDict(extra="forbid")

    colors: List[str] = Field(default_factory=list, max_length=10)
    palettes: List[str] = Field(default_factory=list, max_length=10)
    materials: List[str] = Field(default_factory=list, max_length=10)
    product_types: List[str] = Field(default_factory=list, max_length=10)


class StyleProfile(BaseModel):
    """What the stylist has learned about the shopper's need in this conversation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = PROFILE_SCHEMA_VERSION

    # Catalogue-backed (validated against live attributes)
    occasion: Optional[str] = Field(default=None, max_length=24)
    department: Optional[str] = Field(default=None, max_length=16)
    product_types: List[str] = Field(default_factory=list, max_length=10)
    colors: List[str] = Field(default_factory=list, max_length=10)
    palettes: List[str] = Field(default_factory=list, max_length=10)
    materials: List[str] = Field(default_factory=list, max_length=10)
    sizes: List[str] = Field(default_factory=list, max_length=6)
    budget_min_inr: Optional[Decimal] = Field(default=None, ge=0)
    budget_max_inr: Optional[Decimal] = Field(default=None, gt=0)
    avoid: AvoidList = Field(default_factory=AvoidList)

    # Conversational context (short free text, never sent to search)
    recipient: Optional[str] = Field(default=None, max_length=40)
    location: Optional[str] = Field(default=None, max_length=60)
    timing: Optional[str] = Field(default=None, max_length=60)

    # 0..1 confidence per field name, e.g. {"occasion": 0.95, "palettes": 0.7}
    confidence: Dict[str, float] = Field(default_factory=dict)

    @field_validator("recipient", "location", "timing")
    @classmethod
    def _no_sensitive_numbers(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and _LONG_NUMBER.search(value):
            raise ValueError("must not contain long numbers (no IDs, phone or payment details)")
        return value.strip() if value else value

    @field_validator("confidence")
    @classmethod
    def _confidence_range(cls, value: Dict[str, float]) -> Dict[str, float]:
        unknown = set(value) - set(cls.model_fields)
        if unknown:
            raise ValueError(f"unknown confidence keys: {sorted(unknown)}")
        if any(not 0.0 <= v <= 1.0 for v in value.values()):
            raise ValueError("confidence values must be between 0 and 1")
        return value

    def is_empty(self) -> bool:
        return self == StyleProfile()


class TurnTrace(BaseModel):
    """What happened in one stylist turn — stored in the audit log for traceability."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str = Field(max_length=32)
    route: str = Field(max_length=24)
    plan: str = Field(max_length=24)
    tools_called: List[str] = Field(default_factory=list, max_length=12)
    product_ids_shown: List[str] = Field(default_factory=list, max_length=12)
    critic_attempts: int = Field(default=0, ge=0, le=5)
    critic_passed: bool = True
    llm_used: bool = False


class ProfileSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: StyleProfile
    turn: Optional[TurnTrace] = None


__all__ = [
    "PROFILE_SCHEMA_VERSION",
    "CATALOG_FIELDS",
    "AvoidList",
    "StyleProfile",
    "TurnTrace",
    "ProfileSaveRequest",
]
