"""Per-size stock: the single owner of every stock change.

Stock lives on ``VariantInventory`` (one row per size). Nothing else may write
those rows; every write here also appends an ``InventoryMovement`` ledger row in
the same transaction, so each unit is traceable and the ledger always sums to
the current levels (see scripts/check_inventory_invariants.py).

Concurrency: rows are locked ``FOR UPDATE`` in ``variant_id`` order (one global
order => no deadlocks between concurrent checkouts), and the DB CHECK
``quantity_available >= 0`` is the last line of defence against overselling.

Semantics (unchanged from the product-level model it replaces):
  available  sellable now
  reserved   held by a pending checkout (already removed from available)
  damaged    not sellable
"""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import ActorContext
from ..models import InventoryMovement, Product, ProductVariant, VariantInventory
from ..models.product import MOVEMENT_TYPES
from ..utils.exceptions import AppError
from .audit_service import record_audit
from .variant_service import active_variants, get_variant, normalize_size

Key = Tuple[str, str]  # (product_id, size)


@dataclass(frozen=True)
class Ref:
    """What caused a movement (order / return / refund / admin)."""

    type: Optional[str] = None
    id: Optional[str] = None
    actor_id: Optional[str] = None
    reason: Optional[str] = None


def merge_lines(lines: Iterable[Any]) -> Dict[Key, int]:
    """``[{product_id, size, quantity}]`` or OrderItem-like objects -> ``{(pid, SIZE): qty}``."""
    merged: Dict[Key, int] = {}
    for line in lines:
        get = line.get if isinstance(line, Mapping) else (lambda k, _l=line: getattr(_l, k))
        key = (str(get("product_id")).strip().upper(), normalize_size(get("size")))
        merged[key] = merged.get(key, 0) + int(get("quantity"))
    return merged


# --------------------------------------------------------------------------- locking


class StockLock:
    """Stock rows locked for the current transaction, keyed by (product_id, size)."""

    def __init__(self, rows: Dict[Key, VariantInventory]):
        self.rows = rows

    def available(self, key: Key) -> int:
        row = self.rows.get(key)
        return int(row.quantity_available) if row is not None else 0

    def shortages(self, db: Session, wanted: Mapping[Key, int]) -> List[Dict[str, Any]]:
        short = [(k, q) for k, q in sorted(wanted.items()) if self.available(k) < q]
        if not short:
            return []
        names = dict(
            db.execute(select(Product.product_id, Product.name).where(Product.product_id.in_({k[0] for k, _ in short}))).all()
        )
        return [
            {
                "product_id": pid,
                "productId": pid,
                "name": names.get(pid, pid),
                "size": size,
                "requested": qty,
                "available": self.available((pid, size)),
            }
            for (pid, size), qty in short
        ]

    def require(self, db: Session, wanted: Mapping[Key, int]) -> None:
        """Raise 409 ``insufficient_stock`` naming every short size."""
        shortages = self.shortages(db, wanted)
        if shortages:
            first = shortages[0]
            raise AppError(
                "insufficient_stock",
                f"Not enough stock for '{first['name']}' ({first['product_id']}) in size {first['size']}: "
                f"requested {first['requested']}, available {first['available']}.",
                409,
                details={"shortages": shortages},
            )


def lock_stock(db: Session, keys: Iterable[Key]) -> StockLock:
    keys = set(keys)
    if not keys:
        return StockLock({})
    variant_keys = {
        vid: (pid, size)
        for vid, pid, size in db.execute(
            select(ProductVariant.variant_id, ProductVariant.product_id, ProductVariant.size).where(
                ProductVariant.product_id.in_({k[0] for k in keys})
            )
        ).all()
        if (pid, size) in keys
    }
    rows = db.scalars(
        select(VariantInventory)
        .where(VariantInventory.variant_id.in_(sorted(variant_keys)))
        .order_by(VariantInventory.variant_id.asc())
        .with_for_update()
        .execution_options(populate_existing=True)  # read the locked values, not a stale identity map
    ).all()
    return StockLock({variant_keys[r.variant_id]: r for r in rows})


# --------------------------------------------------------------------------- movements


def _move(
    db: Session,
    row: VariantInventory,
    movement_type: str,
    ref: Ref,
    *,
    available: int = 0,
    reserved: int = 0,
    damaged: int = 0,
) -> None:
    assert movement_type in MOVEMENT_TYPES, movement_type
    if not (available or reserved or damaged):
        return
    new = (
        row.quantity_available + available,
        row.quantity_reserved + reserved,
        row.quantity_damaged + damaged,
    )
    if min(new) < 0:
        raise AppError(
            "stock_invariant_violation",
            f"Stock change '{movement_type}' would make variant {row.variant_id} negative.",
            409,
            details={"variant_id": row.variant_id, "movement_type": movement_type},
        )
    row.quantity_available, row.quantity_reserved, row.quantity_damaged = new
    db.add(
        InventoryMovement(
            variant_id=row.variant_id,
            movement_type=movement_type,
            delta_available=available,
            delta_reserved=reserved,
            delta_damaged=damaged,
            reference_type=ref.type,
            reference_id=ref.id,
            actor_id=ref.actor_id,
            reason=(ref.reason or None) and ref.reason[:160],
        )
    )


def take(db: Session, lock: StockLock, wanted: Mapping[Key, int], *, movement_type: str, ref: Ref) -> None:
    """Remove units from available: ``sale`` / ``late_capture`` (sold) or ``hold`` (-> reserved)."""
    assert movement_type in ("sale", "hold", "late_capture"), movement_type
    lock.require(db, wanted)
    for key in sorted(wanted):
        qty = wanted[key]
        _move(db, lock.rows[key], movement_type, ref, available=-qty, reserved=qty if movement_type == "hold" else 0)


def release_hold(db: Session, items: Iterable[Any], ref: Ref) -> None:
    """Pending checkout ended without payment: reserved -> available."""
    wanted = merge_lines(items)
    lock = lock_stock(db, wanted)
    for key in sorted(wanted):
        row = lock.rows.get(key)
        if row is not None:
            qty = min(wanted[key], int(row.quantity_reserved))
            _move(db, row, "hold_release", ref, available=qty, reserved=-qty)


def capture_hold(db: Session, items: Iterable[Any], ref: Ref) -> None:
    """Held checkout paid: the reserved units leave stock."""
    wanted = merge_lines(items)
    lock = lock_stock(db, wanted)
    for key in sorted(wanted):
        row = lock.rows.get(key)
        if row is not None:
            _move(db, row, "hold_capture", ref, reserved=-min(wanted[key], int(row.quantity_reserved)))


def restock(db: Session, items: Iterable[Any], *, movement_type: str, ref: Ref) -> None:
    """Sold units come back to the exact sizes they left from (cancel / return)."""
    assert movement_type in ("cancel_restock", "return_restock", "restock"), movement_type
    wanted = merge_lines(items)
    lock = lock_stock(db, wanted)
    for key in sorted(wanted):
        row = lock.rows.get(key)
        if row is not None:
            _move(db, row, movement_type, ref, available=wanted[key])


def split_evenly(total: int, sizes: List[str]) -> Dict[str, int]:
    """Split ``total`` units across ``sizes`` exactly (earlier sizes get the remainder)."""
    base, extra = divmod(max(0, int(total)), max(1, len(sizes)))
    return {size: base + (1 if i < extra else 0) for i, size in enumerate(sizes)}


def open_balance(db: Session, variant: ProductVariant, quantity: int, ref: Ref, low_stock_threshold: Optional[int] = None) -> None:
    """First stock of a size (seed, product creation). Creates the row if needed."""
    if variant.stock is None:
        variant.stock = VariantInventory(quantity_available=0, quantity_reserved=0, quantity_damaged=0)
    if low_stock_threshold is not None:
        variant.stock.low_stock_threshold = int(low_stock_threshold)
    db.flush()
    _move(db, variant.stock, "opening_balance", ref, available=int(quantity))


# --------------------------------------------------------------------------- admin operations


def set_levels(
    db: Session, actor: ActorContext, product: Product, levels: Mapping[str, int], reason: str
) -> Dict[str, Any]:
    """Set absolute available stock per size (stock count / correction)."""
    if not levels:
        raise AppError("validation_error", "Provide at least one size level, e.g. {\"M\": 10}.", 422)
    targets = {get_variant(product, size).size: int(qty) for size, qty in levels.items()}
    if any(q < 0 for q in targets.values()):
        raise AppError("validation_error", "Stock levels cannot be negative.", 422)
    lock = lock_stock(db, {(product.product_id, s) for s in targets})
    ref = Ref("admin", product.product_id, actor.actor_id, reason)
    changes = {}
    for size, qty in sorted(targets.items()):
        row = lock.rows[(product.product_id, size)]
        before = int(row.quantity_available)
        _move(db, row, "adjustment", ref, available=qty - before)
        changes[size] = {"before": before, "after": qty}
    record_audit(db, actor, "inventory", product.product_id, "set_stock_levels", {"sizes": changes}, reason)
    db.commit()
    return stock_summary(product, include_sizes=True)


def receive_units(
    db: Session, actor: ActorContext, product: Product, size: str, quantity: int, reason: str
) -> Dict[str, Any]:
    """Add newly received units to one size."""
    if int(quantity) <= 0:
        raise AppError("validation_error", "Restock quantity must be greater than zero.", 422)
    variant = get_variant(product, size)
    ref = Ref("admin", product.product_id, actor.actor_id, reason)
    restock(db, [{"product_id": product.product_id, "size": variant.size, "quantity": quantity}], movement_type="restock", ref=ref)
    record_audit(db, actor, "inventory", product.product_id, "restock", {"size": variant.size, "quantity": int(quantity)}, reason)
    db.commit()
    return stock_summary(product, include_sizes=True)


# --------------------------------------------------------------------------- read side


def size_available(product: Product, size: str) -> int:
    variant = get_variant(product, size)
    return int(variant.stock.quantity_available) if variant.stock else 0


def stock_summary(product: Product, include_sizes: bool = False) -> Dict[str, Any]:
    """Stock as every API payload exposes it (active sizes, display order)."""
    live = sorted(active_variants(product), key=lambda v: (v.position, v.size))
    rows = [(v, v.stock) for v in live]
    summary: Dict[str, Any] = {
        "product_id": product.product_id,
        "stock": sum(s.quantity_available for _, s in rows if s),
        "quantity_reserved": sum(s.quantity_reserved for _, s in rows if s),
        "quantity_damaged": sum(s.quantity_damaged for _, s in rows if s),
        "stock_by_size": {v.size: (s.quantity_available if s else 0) for v, s in rows},
        "low_stock_alert": any((s.quantity_available if s else 0) <= (s.low_stock_threshold if s else 0) for v, s in rows),
    }
    if include_sizes:
        summary["sizes"] = [
            {
                "size": v.size,
                "sku": v.sku,
                "quantity_available": s.quantity_available if s else 0,
                "quantity_reserved": s.quantity_reserved if s else 0,
                "quantity_damaged": s.quantity_damaged if s else 0,
                "low_stock_threshold": s.low_stock_threshold if s else 0,
                "low_stock_alert": (s.quantity_available if s else 0) <= (s.low_stock_threshold if s else 0),
            }
            for v, s in rows
        ]
    return summary


def list_movements(db: Session, product: Product, limit: int = 100) -> List[Dict[str, Any]]:
    sizes = {v.variant_id: v.size for v in product.variants}
    rows = db.scalars(
        select(InventoryMovement)
        .where(InventoryMovement.variant_id.in_(sizes))
        .order_by(InventoryMovement.created_at.desc(), InventoryMovement.movement_id.desc())
        .limit(max(1, min(int(limit), 500)))
    ).all()
    return [
        {
            "movement_id": m.movement_id,
            "size": sizes[m.variant_id],
            "movement_type": m.movement_type,
            "delta_available": m.delta_available,
            "delta_reserved": m.delta_reserved,
            "delta_damaged": m.delta_damaged,
            "reference_type": m.reference_type,
            "reference_id": m.reference_id,
            "actor_id": m.actor_id,
            "reason": m.reason,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]
