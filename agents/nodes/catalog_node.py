import re
from typing import Optional

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.product_tools import CatalogTools

PRODUCT_ID_RE = re.compile(r"\b(PRD-\d{3}(?:-[A-Z0-9-]+)?)\b", re.IGNORECASE)
PRICE_RE = re.compile(r"(?:under|below|max|upto|up\s+to|<=?)\s*(?:inr|rs\.?|₹)?\s*([\d,]+)", re.IGNORECASE)


def run_catalog_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = CatalogTools(client)
    msg = state.request.message
    msg_lower = msg.lower()

    prod_match = PRODUCT_ID_RE.search(msg)
    product_id = state.request.context.get("product_id") or (prod_match.group(1).upper() if prod_match else None)

    if "recommend" in msg_lower or "pair" in msg_lower or "complete the look" in msg_lower:
        target_id = product_id or "PRD-001"
        code, recs = tools.get_recommendations(
            target_id,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        if code == 200 and isinstance(recs, list):
            names = [f"{r['product_id']} {r['name']} (INR {r['mrp_inr']})" for r in recs]
            state.status = "answer"
            state.data = {"source_product_id": target_id, "recommendations": recs}
            state.reply = (
                f"Recommended Noir Atelier pairings for {target_id}: "
                + (", ".join(names) if names else "No pairings found.")
            )
            return state

    if product_id and any(k in msg_lower for k in ("detail", "fabric", "care", "size", "fit", "stock", "hsn", "price", "prd-")):
        code, prod = tools.get_product_details(
            product_id,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        if code == 200 and isinstance(prod, dict):
            state.status = "answer"
            state.data = {"product": prod}
            state.reply = (
                f"{prod['name']} ({prod['product_id']}, {prod['department']}) — "
                f"MRP INR {prod['mrp_inr']} (HSN {prod['hsn_code']}). "
                f"Sizes: {', '.join(prod.get('sizes_available', []))}. "
                f"Fit: {prod['fit_guide']} Fabric & Care: {prod['fabric_and_care']} "
                f"Available stock: {prod.get('stock', 0)}."
            )
            return state

    if "categor" in msg_lower or "department" in msg_lower:
        code, cats = tools.list_categories(trace_id=state.trace_id, traces=state.tool_traces)
        if code == 200 and isinstance(cats, list):
            state.status = "answer"
            state.data = {"categories": cats}
            summary = ", ".join(f"{c['name']} ({c['category_id']})" for c in cats)
            state.reply = f"Noir Atelier offers strictly premium garments across 3 departments: {summary}."
            return state

    department: Optional[str] = state.request.context.get("department")
    if not department:
        if re.search(r"\bwomen'?s?\b", msg_lower):
            department = "WOMEN"
        elif re.search(r"\bmen'?s?\b", msg_lower):
            department = "MEN"
        elif re.search(r"\bkids'?\b|\bchildren\b", msg_lower):
            department = "KIDS"

    max_price: Optional[float] = state.request.context.get("max_price")
    if max_price is None:
        pm = PRICE_RE.search(msg)
        if pm:
            max_price = float(pm.group(1).replace(",", ""))

    code, items = tools.search_products(
        q=msg if not department and max_price is None else None,
        department=department,
        max_price=max_price,
        in_stock_only="in stock" in msg_lower,
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    if code == 200 and isinstance(items, list) and not items and (department or max_price):
        code, items = tools.search_products(
            department=department,
            max_price=max_price,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )

    state.status = "answer"
    state.data = {"products": items if isinstance(items, list) else []}
    if isinstance(items, list) and items:
        lines = [
            f"{p['product_id']}: {p['name']} ({p['department']}) — INR {p['mrp_inr']} [Sizes: {', '.join(p.get('sizes_available', []))}]"
            for p in items
        ]
        state.reply = "Here are the matching Noir Atelier garments:\n- " + "\n- ".join(lines)
    else:
        state.reply = "No matching Noir Atelier garments were found for your criteria."
    return state
