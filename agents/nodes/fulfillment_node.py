import re

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.order_tools import FulfillmentTools

SHIP_OR_ORD_RE = re.compile(r"\b((?:SHP|ORD)-\d{4})\b", re.IGNORECASE)
PRODUCT_ID_RE = re.compile(r"\b(PRD-\d{3})\b", re.IGNORECASE)


def run_fulfillment_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = FulfillmentTools(client)
    msg = state.request.message
    msg_lower = msg.lower()
    customer_id = state.request.customer_id or "CUS-001"

    match = SHIP_OR_ORD_RE.search(msg)
    identifier = (
        state.request.context.get("shipment_id")
        or state.request.context.get("order_id")
        or (match.group(1).upper() if match else None)
    )

    if "reserve" in msg_lower and "inventory" in msg_lower:
        pm = PRODUCT_ID_RE.search(msg)
        pid = state.request.context.get("product_id") or (pm.group(1).upper() if pm else "PRD-001")
        qty = int(state.request.context.get("quantity", 1))
        code, payload = tools.reserve_inventory(
            pid,
            qty,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.data = payload if isinstance(payload, dict) else {}
        state.status = "action_completed" if code == 200 else "error"
        state.reply = (
            f"Reserved {qty} unit(s) of {pid}. Remaining available: {payload.get('quantity_available')}."
            if code == 200 and isinstance(payload, dict)
            else "Failed to reserve stock."
        )
        return state

    if "schedule" in msg_lower or "dispatch" in msg_lower:
        if not identifier:
            state.status = "clarify_missing_info"
            state.reply = "Please provide the order ID (e.g., ORD-1001) to schedule courier pickup."
            return state
        carrier = state.request.context.get("carrier", "Noir Express")
        code, payload = tools.schedule_shipment(
            identifier,
            carrier=carrier,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.data = payload if isinstance(payload, dict) else {}
        if code == 200 and isinstance(payload, dict):
            state.status = "action_completed"
            state.reply = (
                f"Shipment {payload['shipment_id']} scheduled for {payload['order_id']} via {payload['carrier']} "
                f"(Tracking: {payload['tracking_number']}, Status: {payload['status']})."
            )
        else:
            state.status = "error"
            state.reply = payload.get("message", "Could not schedule shipment.")
        return state

    if not identifier:
        state.status = "clarify_missing_info"
        state.reply = "Please share your order ID (`ORD-1001`) or shipment ID (`SHP-1001`) to track delivery."
        return state

    code, payload = tools.get_shipment(
        identifier,
        customer_id=customer_id,
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    state.data = payload if isinstance(payload, dict) else {}
    if code == 200 and isinstance(payload, dict):
        state.status = "answer"
        state.reply = (
            f"Shipment {payload['shipment_id']} for order {payload['order_id']} is '{payload['status']}' "
            f"via {payload['carrier']} (Tracking: {payload['tracking_number']})."
        )
    else:
        state.status = "answer"
        state.reply = payload.get("message", f"No active shipment found for {identifier}.")
    return state
