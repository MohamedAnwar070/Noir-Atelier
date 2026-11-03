import re
from typing import Any, Dict, List

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


def _format_materials(prod: Dict[str, Any]) -> str:
    mats = prod.get("materials") or []
    if mats:
        return ", ".join(
            f"{int(m['percentage']) if float(m['percentage']).is_integer() else m['percentage']}% {m['name']}"
            for m in mats
        )
    return prod.get("fabric_and_care", "")


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
            composition = _format_materials(prod)
            state.data = {
                "product": prod,
                "products": [prod],
                "action_feedback": {
                    "type": "product_details",
                    "badge": f"{prod['department']} · {prod.get('category', {}).get('name', 'Collection')}",
                    "title": prod["name"],
                    "summary": f"{format_price_range(prod)} · {prod.get('color', '')} · Sizes: {', '.join(prod.get('sizes_available', []))} · {prod.get('stock', 0)} in stock",
                },
            }
            state.reply = (
                f"Here are the details for the {prod['name']} ({prod['department']}):\n"
                f"• Price: {format_price_range(prod)} (incl. GST)\n"
                f"• Price by size: {format_size_prices(prod)}\n"
                f"• Colour: {prod.get('color', 'Signature')}\n"
                f"• Composition: {composition}\n"
                f"• Fit: {prod['fit_guide']}\n"
                f"• Fabric & Care: {prod['fabric_and_care']}\n"
                f"• Availability: {prod.get('stock', 0)} pieces ready to ship"
            )
            return state

    if "categor" in msg_lower or "department" in msg_lower or "taxonomy" in msg_lower:
        code, meta = tools.get_catalog_meta(trace_id=state.trace_id, traces=state.tool_traces)
        if code == 200 and isinstance(meta, dict):
            departments = meta.get("departments", [])
            categories = meta.get("categories", [])
            state.status = "answer"
            state.data = {"departments": departments, "categories": categories}
            dept_summary = ", ".join(d["name"] for d in departments)
            cat_summary = ", ".join(c["name"] for c in categories)
            state.reply = (
                f"We curate tailored garments across {len(departments)} departments ({dept_summary}) "
                f"and {len(categories)} garment categories ({cat_summary}). "
                f"Which department, style, colour or fabric would you like to explore?"
            )
            return state

    ctx = state.request.context
    generic_browse = is_generic_browse_query(msg)
    search_q = None if generic_browse else msg

    code, search_res = tools.search_catalog(
        q=search_q,
        department=ctx.get("department"),
        category=ctx.get("category"),
        color=ctx.get("color"),
        material=ctx.get("material"),
        min_price=ctx.get("min_price"),
        max_price=ctx.get("max_price"),
        in_stock_only=bool(ctx.get("in_stock_only") or "in stock" in msg_lower),
        sort=str(ctx.get("sort") or "featured"),
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )

    payload = search_res if (code == 200 and isinstance(search_res, dict)) else {}
    product_list: List[Dict[str, Any]] = payload.get("items", []) if isinstance(payload.get("items"), list) else []
    interpretation: Dict[str, Any] = payload.get("interpretation", {}) if isinstance(payload.get("interpretation"), dict) else {}
    recognized = interpretation.get("recognized") or []
    recognized_labels = [r.get("label", r.get("value", "")) for r in recognized if r.get("label") or r.get("value")]
    eff_min = interpretation.get("min_price")
    eff_max = interpretation.get("max_price")

    price_desc = ""
    if eff_min is not None and eff_max is not None:
        price_desc = f" between {format_inr(eff_min)} and {format_inr(eff_max)}"
    elif eff_max is not None:
        price_desc = f" under {format_inr(eff_max)}"
    elif eff_min is not None:
        price_desc = f" from {format_inr(eff_min)}"

    title_label = " · ".join(recognized_labels) if recognized_labels else "Curated Noir Atelier Pieces"

    state.status = "answer"
    state.data = {
        "products": product_list,
        "total": payload.get("total", len(product_list)),
        "interpretation": interpretation,
        "action_feedback": {
            "type": "catalog_results",
            "badge": f"{len(product_list)} Piece(s) Available",
            "title": title_label,
            "summary": (
                f"Showing {len(product_list)} garment(s){price_desc}"
                + ". Click any piece below to add to your bag or buy instantly."
            ),
        },
    }
    if product_list:
        lines = [
            f"• {p['name']} ({p['department']} · {p.get('color', '')}) — {format_price_range(p)} · Sizes: {', '.join(p.get('sizes_available', []))}"
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
