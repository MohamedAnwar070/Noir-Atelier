from typing import Any, Dict, Optional

from pydantic import BaseModel


class ConfigUpdateRequest(BaseModel):
    config_key: str
    config_value: Dict[str, Any]
    reason: str


class CustomerCreateRequest(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    loyalty_tier: str = "STANDARD"


class CustomerUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class AddressCreateRequest(BaseModel):
    label: str = "Home"
    street: str
    city: str
    state: str = "Tamil Nadu"
    pin_code: str
    is_primary: bool = False


class CustomerDTO(BaseModel):
    customer_id: str
    name: str
    email: str
    phone: Optional[str]
    loyalty_tier: str
    status: str


class AddressDTO(BaseModel):
    address_id: str
    customer_id: str
    label: str
    street: str
    city: str
    state: str
    pin_code: str
    country: str
    is_primary: bool
