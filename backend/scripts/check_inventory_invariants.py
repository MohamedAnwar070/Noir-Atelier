"""Verify the stock ledger: for every size, the movements sum to its current levels.

Usage (from the repo root):  python -m backend.scripts.check_inventory_invariants
Exit code 0 = consistent, 1 = problems found (printed). Safe to run any time (read-only).
"""

import sys
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.database import get_sync_engine
from backend.app.models import InventoryMovement, ProductVariant, VariantInventory


def find_problems(engine: Optional[Engine] = None) -> List[str]:
    ledger = (
        select(
            InventoryMovement.variant_id,
            func.sum(InventoryMovement.delta_available).label("a"),
            func.sum(InventoryMovement.delta_reserved).label("r"),
            func.sum(InventoryMovement.delta_damaged).label("d"),
        )
        .group_by(InventoryMovement.variant_id)
        .subquery()
    )
    rows = select(
        ProductVariant.product_id,
        ProductVariant.size,
        VariantInventory.quantity_available,
        VariantInventory.quantity_reserved,
        VariantInventory.quantity_damaged,
        func.coalesce(ledger.c.a, 0),
        func.coalesce(ledger.c.r, 0),
        func.coalesce(ledger.c.d, 0),
    ).select_from(ProductVariant).outerjoin(
        VariantInventory, VariantInventory.variant_id == ProductVariant.variant_id
    ).outerjoin(ledger, ledger.c.variant_id == ProductVariant.variant_id)

    problems: List[str] = []
    with Session(engine or get_sync_engine()) as db:
        for pid, size, a, r, d, la, lr, ld in db.execute(rows).all():
            if a is None:
                problems.append(f"{pid} {size}: no stock row")
                continue
            if min(a, r, d) < 0:
                problems.append(f"{pid} {size}: negative stock ({a}/{r}/{d})")
            if (a, r, d) != (la, lr, ld):
                problems.append(f"{pid} {size}: levels {a}/{r}/{d} != ledger {la}/{lr}/{ld} (available/reserved/damaged)")
    return problems


if __name__ == "__main__":
    found = find_problems()
    for line in found:
        print("✗", line)
    print("stock ledger consistent" if not found else f"{len(found)} problem(s)")
    sys.exit(1 if found else 0)
