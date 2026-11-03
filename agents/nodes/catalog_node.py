import re
from typing import Optional

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.product_tools import CatalogTools
from .intent_parser import (
    format_inr,
    format_price_range,
    format_size_prices,
    is_generic_browse_query,
    resolve_product_from_message,
)

PRODUCT_ID_RE = re.compile(r"\b(PRD-\d{3}(?:-[A-Z0-9-]+)?)\b", re.IGNORECASE)
PRICE_RE = re.compile(r"(?:under|below|max|upto|up\s+to|<=?)\s*(?:inr|rs\.?|₹)?\s*([\d,]+)", re.IGNORECASE)


def run_catalog_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = CatalogTools(client)
    msg = state.request.message
    msg_lower = msg.lower()

    prod_match = PRODUCT_ID_RE.search(msg)
    product_id = state.request.context.get("product_id") or (prod_match.group(1).upper() if prod_match else None)

    if not product_id and any(k in msg_lower for k in ("detail", "fabric", "care", "fit", "recommend", "pair")):
        resolved, _ = resolve_product_from_message(msg, state.request.context, client)
        if resolved:
            product_id = resolved.get("product_id")

    if "recommend" in msg_lower or "pair" in msg_lower or "complete the look" in msg_lower:
        target_id = product_id or "PRD-001"
        code, recs = tools.get_recommendations(
            target_id,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        if code == 200 and isinstance(recs, list):
            lines = [f"• {r['name']} ({r['department']}) — {format_price_range(r)}" for r in recs]
            state.status = "answer"
            state.data = {
                "source_product_id": target_id,
                "recommendations": recs,
                "products": recs,
                "action_feedback": {
                    "type": "catalog_recommendations",
                    "badge": "Stylist Pairing",
                    "title": f"{len(recs)} Matching Pieces Found",
                    "summary": f"Curated to pair effortlessly with {target_id}.",
                },
            }
            state.reply = (
                "Here are my recommended pairings to complete your look:\n"
                + ("\n".join(lines) if lines else "No specific pairings found right now.")
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
            state.data = {
                "product": prod,
                "products": [prod],
                "action_feedback": {
                    "type": "product_details",
                    "badge": f"{prod['department']} Collection",
                    "title": prod["name"],
                    "summary": f"{format_price_range(prod)} · Sizes: {', '.join(prod.get('sizes_available', []))} · {prod.get('stock', 0)} in stock",
                },
            }
            state.reply = (
                f"Here are the details for the {prod['name']} ({prod['department']}):\n"
                f"• Price: {format_price_range(prod)} (incl. GST)\n"
                f"• Price by size: {format_size_prices(prod)}\n"
                f"• Fit: {prod['fit_guide']}\n"
                f"• Fabric & Care: {prod['fabric_and_care']}\n"
                f"• Availability: {prod.get('stock', 0)} pieces ready to ship"
            )
            return state

    if "categor" in msg_lower or "department" in msg_lower:
        code, cats = tools.list_categories(trace_id=state.trace_id, traces=state.tool_traces)
        if code == 200 and isinstance(cats, list):
            state.status = "answer"
            state.data = {"categories": cats}
            summary = ", ".join(c["name"] for c in cats)
            state.reply = (
                f"We curate tailored garments across three collections: {summary}. "
                f"Which collection would you like to explore?"
            )
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

    generic_browse = is_generic_browse_query(msg)
    search_q = None if (generic_browse or department or max_price is not None) else msg

    code, items = tools.search_products(
        q=search_q,
        department=department,
        max_price=max_price,
        in_stock_only="in stock" in msg_lower,
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    if code == 200 and isinstance(items, list) and not items:
        code, items = tools.search_products(
            department=department,
            max_price=max_price,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )

    state.status = "answer"
    product_list = items if isinstance(items, list) else []
    state.data = {
        "products": product_list,
        "action_feedback": {
            "type": "catalog_results",
            "badge": f"{len(product_list)} Piece(s) Available",
            "title": (
                f"{department.title()} Collection" if department else "Curated Noir Atelier Pieces"
            ),
            "summary": (
                f"Showing {len(product_list)} garment(s)"
                + (f" under {format_inr(max_price)}" if max_price else "")
                + ". Click any piece below to add to your bag or buy instantly."
            ),
        },
    }
    if product_list:
        lines = [
            f"• {p['name']} ({p['department']}) — {format_price_range(p)} · Sizes: {', '.join(p.get('sizes_available', []))}"
            for p in product_list
        ]
        intro = (
            "I'd love to help you shop! Here are our signature pieces available right now:"
            if generic_browse
            else "Here are the pieces that match what you're looking for:"
        )
        state.reply = (
            f"{intro}\n"
            + "\n".join(lines)
            + "\n\nYou can tap Add to Bag or Buy Now on any card below, or tell me which piece and quantity you'd like!"
        )
    else:
        state.reply = "I couldn't find any garments matching those exact filters. Would you like to see our full collection?"
    return state
