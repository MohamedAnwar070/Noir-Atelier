import re

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.ops_tools import InventoryTools

PRODUCT_ID_RE = re.compile(r"\b(PRD-\d{3})\b", re.IGNORECASE)
QTY_RE = re.compile(r"\b(?:to|set|qty|quantity)\s+(\d+)\b", re.IGNORECASE)


def run_inventory_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = InventoryTools(client)
    msg = state.request.message
    msg_lower = msg.lower()

    prod_match = PRODUCT_ID_RE.search(msg)
    product_id = state.request.context.get("product_id") or (prod_match.group(1).upper() if prod_match else None)

    if product_id and "discontinue" in msg_lower:
        code, payload = tools.discontinue_product(
            product_id,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.data = payload if isinstance(payload, dict) else {}
        state.status = "action_completed" if code == 200 else "error"
        state.reply = (
            f"Garment {product_id} has been marked discontinued (soft-deleted) in the catalog."
            if code == 200
            else payload.get("message", f"Could not discontinue {product_id}.")
        )
        return state

    if product_id and ("update" in msg_lower or "set" in msg_lower or "adjust" in msg_lower):
        qm = QTY_RE.search(msg)
        new_qty = int(state.request.context.get("quantity_available") or (qm.group(1) if qm else 25))
        code, payload = tools.update_inventory(
            product_id,
            new_qty,
            size_breakdown=state.request.context.get("size_breakdown"),
            reason="inventory_agent_stock_sync",
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.data = payload if isinstance(payload, dict) else {}
        state.status = "action_completed" if code == 200 else "error"
        state.reply = (
            f"Updated {product_id} available inventory to {new_qty} units."
            if code == 200
            else payload.get("message", "Failed to update inventory.")
        )
        return state

    low_only = "low" in msg_lower or "alert" in msg_lower
    code, items = tools.list_inventory(
        low_stock_only=low_only,
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    state.status = "answer"
    state.data = {"inventory": items if isinstance(items, list) else []}
    if code == 200 and isinstance(items, list):
        total_units = sum(i.get("quantity_available", 0) for i in items)
        state.reply = (
            f"Inventory snapshot across {len(items)} garment SKUs: {total_units} total units available."
        )
    else:
        state.reply = "Unable to retrieve inventory list."
    return state
