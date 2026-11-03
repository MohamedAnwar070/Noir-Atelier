import hashlib
import hmac
import re
from typing import Optional, Union


_HEX_64_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def sign_payload(payload: Union[str, bytes], secret: str) -> str:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def verify_signature(
    raw_body: Optional[Union[str, bytes]],
    header: Optional[str],
    secret: str,
) -> bool:
    if not raw_body or not header or not isinstance(header, str):
        return False
    cleaned = header[len("sha256="):] if header.startswith("sha256=") else header
    cleaned = cleaned.strip()
    if not _HEX_64_RE.match(cleaned):
        return False
    expected_hex = sign_payload(raw_body, secret)
    return hmac.compare_digest(expected_hex.lower(), cleaned.lower())
