import re

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.order_tools import FulfillmentTools

SHIP_OR_ORD_RE = re.compile(r"\b((?:SHP|ORD)-\d{4})\b", re.IGNORECASE)


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

    if "schedule" in msg_lower or "dispatch" in msg_lower:
        if not identifier:
            state.status = "clarify_missing_info"
            state.reply = "Please share your Order ID (for example, ORD-1001) so I can schedule courier dispatch."
            return state
        carrier = state.request.context.get("carrier", "Noir Express")
        code, payload = tools.schedule_shipment(
            identifier,
            carrier=carrier,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        payload_dict = dict(payload) if isinstance(payload, dict) else {}
        if code == 200 and isinstance(payload, dict):
            state.status = "action_completed"
            payload_dict["action_feedback"] = {
                "type": "shipment_scheduled",
                "badge": "Shipment Dispatched",
                "title": f"Order #{payload['order_id']} Dispatched via {payload['carrier']}",
                "summary": f"Tracking Number: {payload['tracking_number']} · Shipment #{payload['shipment_id']}",
                "details": [
                    {"label": "Order ID", "value": payload["order_id"]},
                    {"label": "Shipment ID", "value": payload["shipment_id"]},
                    {"label": "Courier", "value": payload["carrier"]},
                    {"label": "Tracking AWB", "value": payload["tracking_number"]},
                ],
                "cta_label": "Track in My Orders",
                "cta_page": "orders",
            }
            state.data = payload_dict
            state.reply = (
                f"Your order (#{payload['order_id']}) has been dispatched via {payload['carrier']}! "
                f"Your tracking number is {payload['tracking_number']}."
            )
        else:
            state.status = "error"
            state.data = payload_dict
            state.reply = payload_dict.get("message", "Could not schedule shipment right now.")
        return state

    if not identifier:
        state.status = "clarify_missing_info"
        state.reply = "Please share your Order ID (e.g., ORD-1001) or Shipment ID (e.g., SHP-1001) so I can track your delivery."
        return state

    code, payload = tools.get_shipment(
        identifier,
        customer_id=customer_id,
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    payload_dict = dict(payload) if isinstance(payload, dict) else {}
    if code == 200 and isinstance(payload, dict):
        state.status = "answer"
        payload_dict["action_feedback"] = {
            "type": "shipment_tracking",
            "badge": f"Delivery: {str(payload['status']).title()}",
            "title": f"Order #{payload['order_id']} · {payload['carrier']}",
            "summary": f"Tracking AWB: {payload['tracking_number']}",
        }
        state.data = payload_dict
        state.reply = (
            f"Your delivery (#{payload['shipment_id']}) for Order #{payload['order_id']} is currently {payload['status']} "
            f"with {payload['carrier']} (Tracking Number: {payload['tracking_number']})."
        )
    else:
        state.status = "answer"
        state.data = payload_dict
        state.reply = payload_dict.get("message", f"No shipment has been dispatched yet for {identifier}.")
    return state
