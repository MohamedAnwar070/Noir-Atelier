"""Apply reviewed style tags (product → occasions, colour → palettes) to the database.

The tags live in a reviewable JSON file (default: backend/data/style_tags_draft.json).
This script is the only writer, and it is gated on human review:

  * refuses to run unless the file has  "status": "approved"  and  "reviewed_by"
  * validates every product id, colour name, occasion and palette code first
  * syncs (adds AND removes) so the database matches the file exactly
  * runs in one transaction and writes an audit_log entry

Usage:
    python -m backend.scripts.apply_style_tags --dry-run     # show the diff, write nothing
    python -m backend.scripts.apply_style_tags               # apply an approved file
    python -m backend.scripts.apply_style_tags --file other.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.app.auth import ActorContext  # noqa: E402
from backend.app.config import get_settings  # noqa: E402
from backend.app.models import Color, ColorPalette, Occasion, Palette, Product, ProductOccasion  # noqa: E402
from backend.app.services.audit_service import record_audit  # noqa: E402

DEFAULT_FILE = Path(__file__).resolve().parents[1] / "data" / "style_tags_draft.json"


class StyleTagError(ValueError):
    """The tag file is invalid or not approved; nothing was written."""


def load_tag_file(path: Path) -> Dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _validate(db: Session, doc: Dict) -> Tuple[Dict[str, Set[str]], Dict[int, Set[str]]]:
    """Return (product_id → occasion codes, color_id → palette codes) or raise StyleTagError."""
    occasions = set(db.scalars(select(Occasion.code).where(Occasion.is_active.is_(True))))
    palettes = set(db.scalars(select(Palette.code)))
    product_ids = set(db.scalars(select(Product.product_id)))
    color_ids = {c.name: c.color_id for c in db.scalars(select(Color))}

    errors: List[str] = []
    wanted_occasions: Dict[str, Set[str]] = {}
    for entry in doc.get("product_occasions", []):
        pid = entry.get("product_id")
        if pid not in product_ids:
            errors.append(f"unknown product_id {pid!r}")
            continue
        codes = set(entry.get("occasions") or [])
        if not codes:
            errors.append(f"{pid}: at least one occasion is required")
        for bad in sorted(codes - occasions):
            errors.append(f"{pid}: unknown occasion {bad!r}")
        wanted_occasions[pid] = codes & occasions

    wanted_palettes: Dict[int, Set[str]] = {}
    for color_name, codes in (doc.get("color_palettes") or {}).items():
        if color_name not in color_ids:
            errors.append(f"unknown colour {color_name!r}")
            continue
        codes = set(codes or [])
        for bad in sorted(codes - palettes):
            errors.append(f"{color_name}: unknown palette {bad!r}")
        wanted_palettes[color_ids[color_name]] = codes & palettes

    if errors:
        raise StyleTagError("Tag file is invalid:\n  - " + "\n  - ".join(errors))
    return wanted_occasions, wanted_palettes


def sync_style_tags(db: Session, doc: Dict, *, dry_run: bool = False, require_approval: bool = True) -> Dict[str, int]:
    """Make product_occasions / color_palettes match ``doc``. Returns change counts."""
    if require_approval and (doc.get("status") != "approved" or not doc.get("reviewed_by")):
        raise StyleTagError(
            "Refusing to apply: set \"status\": \"approved\" and \"reviewed_by\" in the tag file after review."
        )
    wanted_occasions, wanted_palettes = _validate(db, doc)

    current_occ: Dict[str, Set[str]] = {}
    for row in db.scalars(select(ProductOccasion)):
        current_occ.setdefault(row.product_id, set()).add(row.occasion_code)
    current_pal: Dict[int, Set[str]] = {}
    for row in db.scalars(select(ColorPalette)):
        current_pal.setdefault(row.color_id, set()).add(row.palette_code)

    counts = {"occasions_added": 0, "occasions_removed": 0, "palettes_added": 0, "palettes_removed": 0}
    for pid, codes in wanted_occasions.items():
        have = current_occ.get(pid, set())
        for code in codes - have:
            counts["occasions_added"] += 1
            if not dry_run:
                db.add(ProductOccasion(product_id=pid, occasion_code=code))
        for code in have - codes:
            counts["occasions_removed"] += 1
            if not dry_run:
                db.delete(db.get(ProductOccasion, (pid, code)))
    for color_id, codes in wanted_palettes.items():
        have = current_pal.get(color_id, set())
        for code in codes - have:
            counts["palettes_added"] += 1
            if not dry_run:
                db.add(ColorPalette(color_id=color_id, palette_code=code))
        for code in have - codes:
            counts["palettes_removed"] += 1
            if not dry_run:
                db.delete(db.get(ColorPalette, (color_id, code)))

    if not dry_run:
        actor = ActorContext("admin", doc.get("reviewed_by") or "script", "catalog_editor", trace_id="TRC-STYLETAGS")
        record_audit(db, actor, "catalog", "style_tags", "apply_style_tags", counts, "reviewed_style_tag_file")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--dry-run", action="store_true", help="validate and show the diff without writing")
    args = parser.parse_args()

    doc = load_tag_file(args.file)
    engine = create_engine(get_settings().database_sync_url)
    with Session(engine) as db:
        try:
            counts = sync_style_tags(db, doc, dry_run=args.dry_run, require_approval=not args.dry_run)
        except StyleTagError as exc:
            print(exc, file=sys.stderr)
            return 1
        if args.dry_run:
            print("DRY RUN — nothing written:", counts)
            return 0
        db.commit()
    print("Applied:", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
