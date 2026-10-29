import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from ..config import get_settings
from ..utils.id_generator import validate_short_id


PUBLIC_BUCKETS = {"products", "categories"}
PRIVATE_BUCKETS = {"invoices", "labels", "packing", "returns", "tickets", "exports"}

BUCKET_ENTITY_MAP = {
    "products": "product",
    "categories": "category",
    "returns": "return",
    "tickets": "ticket",
}


class LocalObjectStore:
    def __init__(self, root: Optional[Path] = None, media_base_url: Optional[str] = None) -> None:
        settings = get_settings()
        self.root = Path(root or settings.storage_root).resolve()
        self.media_base_url = (media_base_url or settings.media_base_url).rstrip("/")
        self.ensure_base_directories()

    def ensure_base_directories(self) -> None:
        for bucket in PUBLIC_BUCKETS | PRIVATE_BUCKETS:
            (self.root / bucket).mkdir(parents=True, exist_ok=True)
        for dept in ("CAT-MEN", "CAT-WMN", "CAT-KID"):
            (self.root / "categories" / dept).mkdir(parents=True, exist_ok=True)

    def resolve_path(self, bucket: str, entity_folder: str, filename: str) -> Path:
        if bucket not in (PUBLIC_BUCKETS | PRIVATE_BUCKETS):
            raise ValueError(f"Unknown storage bucket: {bucket}")

        required_entity = BUCKET_ENTITY_MAP.get(bucket)
        if required_entity and not validate_short_id(required_entity, entity_folder):
            raise ValueError(f"Invalid short ID '{entity_folder}' for bucket '{bucket}'")

        safe_folder = Path(entity_folder).name
        safe_file = Path(filename).name
        target = (self.root / bucket / safe_folder / safe_file).resolve()
        if not str(target).startswith(str(self.root)):
            raise ValueError("Path traversal blocked")
        return target

    def put_bytes(self, bucket: str, entity_folder: str, filename: str, data: bytes) -> str:
        target = self.resolve_path(bucket, entity_folder, filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return self.relative_key(target)

    def put_json(self, bucket: str, entity_folder: str, filename: str, payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        return self.put_bytes(bucket, entity_folder, filename, raw)

    def get_bytes(self, bucket: str, entity_folder: str, filename: str) -> bytes:
        target = self.resolve_path(bucket, entity_folder, filename)
        if not target.exists():
            raise FileNotFoundError(self.relative_key(target))
        return target.read_bytes()

    def relative_key(self, target: Union[Path, str]) -> str:
        resolved = Path(target).resolve()
        return resolved.relative_to(self.root).as_posix()

    def public_url(self, relative_key: str) -> str:
        top_bucket = relative_key.split("/", 1)[0]
        if top_bucket not in PUBLIC_BUCKETS:
            raise PermissionError(f"Bucket '{top_bucket}' is private and requires authorized download")
        return f"{self.media_base_url}/{relative_key.lstrip('/')}"

