"""Workers: the only code that fetches product facts. They never talk to the shopper.

Each worker is a thin wrapper over a whitelisted API endpoint, called through
PlatformApiClient (policy gate + service account + trace), so the stylist has
no database access and the same guardrails as every other agent.

Production limits (from the stylist design):
  * at most MAX_TOOL_CALLS per turn (ToolBudget) — a runaway plan cannot fan out;
  * every parallel call has a timeout; a slow or failed worker becomes an error
    in WorkerResults, never an exception in the conversation.
"""

import concurrent.futures as futures
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..client import PlatformApiClient
from ..schemas.state import AgentRole, ToolCallTrace
from .contracts import ProductFact, StyleProfile, WorkerResults

MAX_TOOL_CALLS = 6
CALL_TIMEOUT_SEC = 8.0
RESULTS_SHOWN = 4


class ToolBudgetExceeded(RuntimeError):
    pass


@dataclass
class ToolBudget:
    limit: int = MAX_TOOL_CALLS
    used: List[str] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def take(self, tool_name: str) -> None:
        """Reserve one call; raises ToolBudgetExceeded when the turn's budget is spent."""
        with self._lock:
            if len(self.used) >= self.limit:
                raise ToolBudgetExceeded(f"tool budget of {self.limit} calls exhausted (wanted {tool_name})")
            self.used.append(tool_name)


class StylistTools:
    """Whitelisted endpoints for svc-stylist (see agents/gateway.py)."""

    ROLE = AgentRole.STYLIST.value

    def __init__(self, client: PlatformApiClient, *, trace_id: str, on_behalf_of: Optional[str], budget: ToolBudget):
        self._client = client
        self._trace_id = trace_id
        self._on_behalf_of = on_behalf_of
        self.budget = budget
        self.traces: List[ToolCallTrace] = []
        self._traces_lock = Lock()

    def _call(
        self, tool: str, method: str, endpoint: str, *, params=None, json_body=None, budgeted: bool = True
    ) -> Tuple[int, Any]:
        if budgeted:
            self.budget.take(tool)
        local: List[ToolCallTrace] = []
        result = self._client.call(
            self.ROLE,
            tool,
            method,
            endpoint,
            on_behalf_of=self._on_behalf_of,
            trace_id=self._trace_id,
            params=params,
            json_body=json_body,
            traces=local,
        )
        with self._traces_lock:
            self.traces.extend(local)
        return result

    def attributes(self) -> Tuple[int, Any]:
        return self._call("catalog_attributes", "GET", "/api/catalog/attributes")

    def get_profile(self, session_id: str) -> Tuple[int, Any]:
        # Bookkeeping, not discovery: gated and traced, but outside the worker budget.
        return self._call("get_style_profile", "GET", f"/api/agents/sessions/{session_id}/profile", budgeted=False)

    def save_profile(self, session_id: str, body: Dict[str, Any]) -> Tuple[int, Any]:
        return self._call(
            "save_style_profile", "PUT", f"/api/agents/sessions/{session_id}/profile", json_body=body, budgeted=False
        )

    def search(self, params: Dict[str, Any]) -> Tuple[int, Any]:
        return self._call("catalog_search", "GET", "/api/catalog/search", params=params)

    def recommendations(self, product_id: str) -> Tuple[int, Any]:
        return self._call("pairings", "GET", f"/api/products/{product_id}/recommendations")


def run_parallel(tasks: Dict[str, Callable[[], Any]], timeout: float = CALL_TIMEOUT_SEC) -> Dict[str, Any]:
    """Run independent tool calls concurrently. Each value is the result or the exception raised."""
    out: Dict[str, Any] = {}
    with futures.ThreadPoolExecutor(max_workers=max(1, len(tasks))) as pool:
        running = {name: pool.submit(fn) for name, fn in tasks.items()}
        for name, fut in running.items():
            try:
                out[name] = fut.result(timeout=timeout)
            except Exception as exc:  # timeout or tool failure: recorded, never propagated
                out[name] = exc
    return out


# ---------------------------------------------------------------- facts --------


def _gst_rate_pct(price: float, pricing: Dict[str, Any]) -> int:
    threshold = float(pricing.get("gst_slab_threshold_inr") or 0)
    low = float(pricing.get("gst_rate_upto_threshold") or 0)
    high = float(pricing.get("gst_rate_above_threshold") or 0)
    return round((low if price <= threshold else high) * 100)


def fact_from_item(item: Dict[str, Any], pricing: Dict[str, Any]) -> ProductFact:
    """Copy the facts the stylist may state from one API product payload."""
    prices = [float(v["mrp_inr"]) for v in item.get("variants", []) if v.get("is_active", True)]
    low = min(prices) if prices else float(item.get("mrp_inr") or 0)
    high = max(prices) if prices else low
    return ProductFact(
        product_id=item["product_id"],
        name=item["name"],
        department=item.get("department", ""),
        category=(item.get("category") or {}).get("name", ""),
        color=item.get("color", ""),
        materials=[m["family"] for m in item.get("materials", [])],
        price_min=low,
        price_max=high,
        stock=int(item.get("stock") or 0),
        sizes=list(item.get("sizes_available") or []),
        gst_rate_pct=_gst_rate_pct(low, pricing),
    )


def search_params(profile: StyleProfile, *, broaden: bool = False, limit: int = 12) -> Dict[str, Any]:
    """Translate the profile into /api/catalog/search filters.

    ``broaden`` keeps only the hard constraints (department, type, budget) so the
    stylist always has fallback options when the full brief is too narrow.
    """
    params: Dict[str, Any] = {"in_stock_only": True, "limit": limit}
    if profile.department:
        params["department"] = profile.department
    if profile.product_types:
        params["category"] = profile.product_types[0]
    if profile.budget_max_inr is not None:
        params["max_price"] = float(profile.budget_max_inr)
    if profile.budget_min_inr is not None:
        params["min_price"] = float(profile.budget_min_inr)
    if not broaden:
        for key, values in (
            ("color", profile.colors),
            ("material", profile.materials),
            ("palette", profile.palettes),
        ):
            if values:
                params[key] = ",".join(values)
        if profile.occasion:
            params["occasion"] = profile.occasion
    return params


def _avoided(item: Dict[str, Any], profile: StyleProfile) -> bool:
    avoid = profile.avoid
    if item.get("color_family") in avoid.colors:
        return True
    if set(item.get("color_palettes") or []) & set(avoid.palettes):
        return True
    if {m["family"] for m in item.get("materials", [])} & set(avoid.materials):
        return True
    return (item.get("category") or {}).get("slug") in avoid.product_types


def collect_results(
    profile: StyleProfile,
    primary: Any,
    broad: Any,
    pricing: Dict[str, Any],
    exclude_ids: Optional[List[str]] = None,
) -> WorkerResults:
    """Merge the primary and broadened searches into grounded facts (avoid-lists applied)."""
    results = WorkerResults()
    exclude = set(exclude_ids or [])
    chosen: List[Dict[str, Any]] = []

    for label, outcome, relaxed in (("search", primary, False), ("broad_search", broad, True)):
        if isinstance(outcome, Exception):
            results.errors.append(f"{label}: {outcome}")
            continue
        status, payload = outcome
        if status != 200 or not isinstance(payload, dict):
            results.errors.append(f"{label}: HTTP {status}")
            continue
        if not relaxed:
            results.total_matches = int(payload.get("total") or 0)
        for item in payload.get("items", []):
            if len(chosen) >= RESULTS_SHOWN:
                break
            if item["product_id"] in exclude or _avoided(item, profile):
                continue
            if any(c["product_id"] == item["product_id"] for c in chosen):
                continue
            if relaxed and chosen:
                break  # broad results only fill in when the full brief found nothing
            chosen.append(item)
            results.relaxed = results.relaxed or relaxed

    results.products = [fact_from_item(item, pricing) for item in chosen]
    results.display_items = {item["product_id"]: item for item in chosen}
    return results
