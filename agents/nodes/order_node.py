import re

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.order_tools import OrderTools

ORDER_ID_RE = re.compile(r"\b(ORD-\d{4})\b", re.IGNORECASE)
PRODUCT_ID_RE = re.compile(r"\b(PRD-\d{3})\b", re.IGNORECASE)


def run_order_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = OrderTools(client)
    msg = state.request.message
    msg_lower = msg.lower()
    customer_id = state.request.customer_id or "CUS-001"

    ord_match = ORDER_ID_RE.search(msg)
    order_id = state.request.context.get("order_id") or (ord_match.group(1).upper() if ord_match else None)

    if "cancel" in msg_lower:
        if not order_id:
            state.status = "clarify_missing_info"
            state.reply = "Please share your Noir Atelier order ID (e.g., ORD-1001) so I can process the pre-shipment cancellation."
            return state

        code, payload = tools.cancel_order(
            order_id,
            reason=state.request.context.get("reason", "customer_requested_cancellation"),
            customer_id=customer_id,
            request_key=state.request.request_key,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.data = payload if isinstance(payload, dict) else {}
        state.policy_citations.append("POL-CAN-01")
        if code == 200 and isinstance(payload, dict):
            state.status = "action_completed"
            state.reply = (
                f"Order {payload['order_id']} has been cancelled under Tier 0 pre-shipment policy (POL-CAN-01) "
                f"and your payment has been refunded."
            )
        elif code == 403:
            state.status = "blocked_unauthorized"
            state.reply = payload.get("message", "You are not authorized to cancel this order.")
        else:
            state.status = "answer"
            state.reply = payload.get("message", f"Order {order_id} cannot be cancelled at this stage.")
        return state

    if any(k in msg_lower for k in ("place order", "buy", "checkout", "create order", "purchase")):
        items = state.request.context.get("items")
        if not items:
            prod_match = PRODUCT_ID_RE.search(msg)
            pid = prod_match.group(1).upper() if prod_match else "PRD-001"
            items = [{"product_id": pid, "size": state.request.context.get("size", "M"), "quantity": int(state.request.context.get("quantity", 1))}]

        estimated = state.request.context.get("estimated_amount_inr")
        code, payload = tools.create_order(
            customer_id=customer_id,
            items=items,
            session_id=state.request.session_id,
            coupon_code=state.request.context.get("coupon_code"),
            payment_method=state.request.context.get("payment_method", "upi"),
            request_key=state.request.request_key,
            estimated_amount_inr=float(estimated) if estimated is not None else None,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.data = payload if isinstance(payload, dict) else {}
        if code in (200, 201) and isinstance(payload, dict):
            state.status = "action_completed"
            state.reply = (
                f"Order {payload['order_id']} is confirmed! "
                f"Grand Total: INR {payload['grand_total_inr']} (incl. GST INR {payload['total_gst_inr']}). "
                f"Invoice: {payload.get('invoice_id')}."
            )
        elif code == 403:
            state.status = "blocked_unauthorized"
            state.reply = payload.get("message", "Order exceeds autonomous agent ceiling or permission scope.")
        else:
            state.status = "error"
            state.reply = payload.get("message", "Unable to create order.")
        return state

    if not order_id:
        state.status = "clarify_missing_info"
        state.reply = "Could you please provide your Noir Atelier order ID (for example, ORD-1001)?"
        return state

    code, payload = tools.get_order_status(
        order_id,
        customer_id=customer_id,
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    state.data = payload if isinstance(payload, dict) else {}
    if code == 200 and isinstance(payload, dict):
        state.status = "answer"
        state.reply = (
            f"Order {payload['order_id']} status is '{payload['status']}' "
            f"(Payment: {payload['payment_status']}, Total: INR {payload['grand_total_inr']})."
        )
    elif code == 403:
        state.status = "blocked_unauthorized"
        state.reply = payload.get("message", "Unauthorized access to order.")
    else:
        state.status = "answer"
        state.reply = payload.get("message", f"Order {order_id} was not found.")
    return state
