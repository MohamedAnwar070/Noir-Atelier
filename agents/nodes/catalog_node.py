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

    detail_keywords = (
        "detail",
        "fabric",
        "care",
        "size",
        "fit",
        "stock",
        "hsn",
        "price",
        "provenance",
        "origin",
        "drape",
        "tell me",
        "prd-",
    )
    pairing_keywords = ("recommend", "pair", "complete the look", "complete the ensemble", "styling")

    if not product_id and any(k in msg_lower for k in (*detail_keywords, "recommend", "pair")):
        resolved, _ = resolve_product_from_message(msg, state.request.context, client)
        if resolved:
            product_id = resolved.get("product_id")

    # 1. Specific Garment Dossier Consultation (optionally with styling pairings)
    if product_id and any(k in msg_lower for k in detail_keywords):
        # Strip any SKU colour/size suffix when looking up by product_id if needed
        canonical_pid = product_id[:7] if product_id.upper().startswith("PRD-") else product_id
        code, prod = tools.get_product_details(
            canonical_pid,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        if code == 200 and isinstance(prod, dict):
            recs: List[Dict[str, Any]] = []
            if any(k in msg_lower for k in pairing_keywords):
                rec_code, rec_list = tools.get_recommendations(
                    prod["product_id"],
                    trace_id=state.trace_id,
                    traces=state.tool_traces,
                )
                if rec_code == 200 and isinstance(rec_list, list):
                    recs = rec_list

            state.status = "answer"
            composition = _format_materials(prod)
            origin = prod.get("country_of_origin") or "India"
            base_mrp = float(prod.get("mrp_inr") or 0)
            is_high_value = base_mrp >= 50000

            cards = [prod, *[r for r in recs if r.get("product_id") != prod.get("product_id")]]
            state.data = {
                "product": prod,
                "recommendations": recs,
                "products": cards,
                "action_feedback": {
                    "type": "product_details",
                    "badge": f"{prod['department']} · {prod.get('category', {}).get('name', 'Archive')}",
                    "title": prod["name"],
                    "summary": (
                        f"{format_price_range(prod)} · {prod.get('color', '')} · "
                        f"Sizes: {', '.join(prod.get('sizes_available', []))} · {prod.get('stock', 0)} in vault"
                    ),
                },
            }

            assurance_line = (
                "\n• Maison Provenance: Sealed with numbered POL-RET-01 security ribbon; "
                "dispatched via complimentary transit-insured white-glove courier with mandatory signature. "
                "Credit/Debit Card and IMPS/RTGS/NEFT Private Wire supported."
                if is_high_value
                else "\n• Maison Provenance: Accompanied by 4-point hand-tacked woven label and POL-RET-01 security ribbon."
            )
            pairing_block = ""
            if recs:
                rec_lines = [f"  – {r['name']} ({format_price_range(r)})" for r in recs[:3]]
                pairing_block = "\n• Ensemble Pairings:\n" + "\n".join(rec_lines)

            state.reply = (
                f"Allow me to walk you through the **{prod['name']}** ({prod['product_id']} · {prod['department']}):\n"
                f"• Tariff: {format_price_range(prod)} (inclusive of GST · HSN {prod.get('hsn_code', '62')})\n"
                f"• Size Tariffs: {format_size_prices(prod)}\n"
                f"• Colourway & Origin: {prod.get('color', 'Signature')} · Crafted in {origin}\n"
                f"• Natural Fiber Composition: {composition}\n"
                f"• Silhouette & Fit: {prod.get('fit_guide', 'True tailored fit.')}\n"
                f"• Care Protocol: {prod.get('fabric_and_care', 'Specialist garment care.')}\n"
                f"• Vault Availability: {prod.get('stock', 0)} piece(s) ready for dispatch"
                f"{assurance_line}"
                f"{pairing_block}"
            )
            return state

    # 2. Pure Ensemble Pairing Inquiry
    if "recommend" in msg_lower or "pair" in msg_lower or "complete the look" in msg_lower:
        target_id = (product_id[:7] if product_id and product_id.upper().startswith("PRD-") else product_id) or "PRD-001"
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
                    "title": f"{len(recs)} Curated Pairings",
                    "summary": f"Selected from the Noir Atelier archive to complement {target_id}.",
                },
            }
            state.reply = (
                f"To complement {target_id}, I recommend these pieces from our archive:\n"
                + ("\n".join(lines) if lines else "No specific pairings are registered for this piece yet.")
            )
            return state

    # 3. Archive Taxonomy & Department Overview
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
                f"Noir Atelier curates natural-fiber garments across {len(departments)} departments ({dept_summary}) "
                f"and {len(categories)} silhouettes ({cat_summary}). "
                f"Which department, natural fiber, colourway, or price edition may I present for you?"
            )
            return state

    # 4. Natural-Language Archive Search
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
    total_matches = int(payload.get("total", len(product_list)))
    interpretation: Dict[str, Any] = payload.get("interpretation", {}) if isinstance(payload.get("interpretation"), dict) else {}
    recognized = interpretation.get("recognized") or []
    recognized_labels = [r.get("label", r.get("value", "")) for r in recognized if r.get("label") or r.get("value")]
    eff_min = interpretation.get("min_price")
    eff_max = interpretation.get("max_price")

    price_desc = ""
    if eff_min is not None and eff_max is not None:
        price_desc = f" between {format_inr(eff_min)} and {format_inr(eff_max)}"
    elif eff_max is not None:
        price_desc = f" up to {format_inr(eff_max)}"
    elif eff_min is not None:
        price_desc = f" from {format_inr(eff_min)}"

    title_label = " · ".join(recognized_labels) if recognized_labels else "Curated Noir Atelier Archive"

    state.status = "answer"
    state.data = {
        "products": product_list,
        "total": total_matches,
        "interpretation": interpretation,
        "action_feedback": {
            "type": "catalog_results",
            "badge": f"{total_matches} Archive Piece(s)",
            "title": title_label,
            "summary": (
                f"Presenting {len(product_list)} of {total_matches} curated garment(s){price_desc}. "
                "Inspect any dossier or add directly to your bag below."
            ),
        },
    }
    if product_list:
        featured_slice = product_list[:6]
        lines = []
        for p in featured_slice:
            comp = _format_materials(p)
            comp_tag = f" · {comp}" if comp else ""
            lines.append(
                f"• {p['name']} ({p['product_id']} · {p['department']} · {p.get('color', '')}{comp_tag}) — "
                f"{format_price_range(p)} · Sizes: {', '.join(p.get('sizes_available', []))}"
            )
        more_note = (
            f"\n*(Showing {len(featured_slice)} highlights of {total_matches} matching archive pieces.)*"
            if total_matches > len(featured_slice)
            else ""
        )
        intro = (
            "Welcome to the Noir Atelier archive. Here is a curated selection of standout garments currently in our vault:"
            if generic_browse
            else f"I have selected {total_matches} piece(s) from our archive{price_desc} matching your criteria:"
        )
        state.reply = (
            f"{intro}\n"
            + "\n".join(lines)
            + more_note
            + "\n\nSelect **Dossier** on any card below to inspect full fiber provenance and GST details, or ask me about a specific `PRD-XXX` reference."
        )
    else:
        state.reply = (
            "No garments in our 100-piece archive matched that exact combination. "
            "May I suggest broadening the colourway or price edition, or presenting our signature silk, linen, and cashmere highlights?"
        )
    return state
