import re

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.refund_tools import ReturnsTools
from .intent_parser import format_inr

ORDER_ID_RE = re.compile(r"\b(ORD-\d{4})\b", re.IGNORECASE)
RETURN_ID_RE = re.compile(r"\b(RET-\d{4})\b", re.IGNORECASE)
REFUND_ID_RE = re.compile(r"\b(RFD-\d{4})\b", re.IGNORECASE)


def run_returns_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = ReturnsTools(client)
    msg = state.request.message
    msg_lower = msg.lower()
    customer_id = state.request.customer_id or "CUS-001"

    rfd_match = REFUND_ID_RE.search(msg)
    refund_id = state.request.context.get("refund_id") or (rfd_match.group(1).upper() if rfd_match else None)

    if refund_id and ("approve" in msg_lower or "process" in msg_lower):
        if "process" in msg_lower:
            code, payload = tools.process_refund(
                refund_id,
                trace_id=state.trace_id,
                traces=state.tool_traces,
            )
            payload_dict = dict(payload) if isinstance(payload, dict) else {}
            state.status = "action_completed" if code == 200 else "error"
            if code == 200 and isinstance(payload, dict):
                payload_dict["action_feedback"] = {
                    "type": "refund_processed",
                    "badge": "Refund Paid Out",
                    "title": f"Refund #{refund_id} Disbursed",
                    "summary": f"Payment Reference: {payload.get('payment_refund_id')}",
                    "cta_label": "View in Orders & Returns",
                    "cta_page": "orders",
                }
                state.reply = (
                    f"Refund #{refund_id} has been paid out to the original payment method "
                    f"(Reference: {payload.get('payment_refund_id')})."
                )
            else:
                state.reply = payload_dict.get("message", "Could not process refund.")
            state.data = payload_dict
            return state

        override_token = None
        if state.request.actor_role == "manager":
            override_token = "admin_manager"
        elif state.request.actor_role == "finance_admin":
            override_token = "admin_finance"

        code, payload = tools.approve_refund(
            refund_id,
            reason=state.request.context.get("reason", "policy_verified_qc_passed"),
            override_token=override_token,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        payload_dict = dict(payload) if isinstance(payload, dict) else {}
        if code == 200 and isinstance(payload, dict):
            state.status = "action_completed" if payload["status"] == "approved" else "pending_approval"
            payload_dict["action_feedback"] = {
                "type": "refund_approved",
                "badge": "Refund Approved" if payload["status"] == "approved" else "Awaiting Second Approval",
                "title": f"Refund #{payload['refund_id']} — {str(payload['status']).replace('_', ' ').title()}",
                "summary": f"Amount: {format_inr(payload.get('amount_inr', 0))} · Order #{payload.get('order_id', '')}",
                "cta_label": "Open Admin Console",
                "cta_page": "admin",
            }
            state.data = payload_dict
            state.reply = (
                f"Refund #{payload['refund_id']} has been approved and is ready for payout."
                if payload["status"] == "approved"
                else f"Refund #{payload['refund_id']} has been approved by {state.request.actor_role} and is awaiting final Finance sign-off."
            )
        elif code == 403:
            state.status = "blocked_unauthorized"
            state.data = payload_dict
            state.reply = payload_dict.get("message", "Refund approval requires Store Manager or Finance Admin access.")
        else:
            state.status = "error"
            state.data = payload_dict
            state.reply = payload_dict.get("message", "Could not approve refund.")
        return state

    ret_match = RETURN_ID_RE.search(msg)
    return_id = state.request.context.get("return_id") or (ret_match.group(1).upper() if ret_match else None)
    if return_id and ("status" in msg_lower or "track" in msg_lower or "check" in msg_lower):
        code, payload = tools.get_return_status(
            return_id,
            customer_id=customer_id,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        payload_dict = dict(payload) if isinstance(payload, dict) else {}
        state.status = "answer"
        state.data = payload_dict
        if code == 200 and isinstance(payload, dict):
            state.reply = (
                f"Your Return #{payload['return_id']} for Order #{payload['order_id']} is currently "
                f"{str(payload['status']).replace('_', ' ')} (Refund #{payload['refund_id']}: {payload['refund_status']})."
            )
        else:
            state.reply = payload_dict.get("message", f"Return {return_id} was not found.")
        return state

    ord_match = ORDER_ID_RE.search(msg)
    order_id = state.request.context.get("order_id") or (ord_match.group(1).upper() if ord_match else None)
    if not order_id:
        state.status = "clarify_missing_info"
        state.reply = (
            "I can start your return right away! Please share your Order ID (for example, ORD-1001) and let me know the reason for your return."
        )
        return state

    tag_intact = bool(state.request.context.get("tag_intact", "tag removed" not in msg_lower and "cut tag" not in msg_lower))
    qc_passed = bool(state.request.context.get("qc_passed", "worn" not in msg_lower and "stained" not in msg_lower))
    is_defective = bool(state.request.context.get("is_defective_claim", "defect" in msg_lower or "damaged" in msg_lower))
    reason_cat = state.request.context.get("reason_category", "defective_garment" if is_defective else "size_mismatch")

    code, payload = tools.initiate_return(
        order_id,
        reason_category=reason_cat,
        customer_notes=msg,
        tag_intact=tag_intact,
        qc_passed=qc_passed,
        is_defective_claim=is_defective,
        customer_id=customer_id,
        request_key=state.request.request_key,
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    payload_dict = dict(payload) if isinstance(payload, dict) else {}
    state.policy_citations.extend(["POL-RET-01", "POL-RET-02"])

    if code in (200, 201) and isinstance(payload, dict):
        tier = payload.get("approval_tier", 1)
        if tier == 1:
            state.status = "action_completed"
            payload_dict["action_feedback"] = {
                "type": "return_completed",
                "badge": "Instant Refund Processed",
                "title": f"Return #{payload['return_id']} Approved & Refunded",
                "summary": f"Refund #{payload['refund_id']} for Order #{payload['order_id']} has been processed automatically.",
                "details": [
                    {"label": "Return ID", "value": payload["return_id"]},
                    {"label": "Order ID", "value": payload["order_id"]},
                    {"label": "Refund ID", "value": payload["refund_id"]},
                    {"label": "Status", "value": "Processed & Restocked"},
                ],
                "cta_label": "View My Returns",
                "cta_page": "orders",
            }
            state.reply = (
                f"Your return (#{payload['return_id']}) for Order #{payload['order_id']} has been approved! "
                f"Refund #{payload['refund_id']} has been processed back to your original payment method."
            )
        elif tier == 2:
            state.status = "pending_approval"
            payload_dict["action_feedback"] = {
                "type": "return_pending_approval",
                "badge": "Sent for Manager Review",
                "title": f"Return #{payload['return_id']} Logged for Priority Review",
                "summary": f"Because this piece is over ₹5,000, our Store Manager is reviewing Refund #{payload['refund_id']} (Ticket #{payload.get('escalation_ticket_id')}).",
                "cta_label": "Track Return Status",
                "cta_page": "orders",
            }
            state.reply = (
                f"I've registered your return (#{payload['return_id']}) for Order #{payload['order_id']}. "
                f"Because this luxury garment is valued between ₹5,001 and ₹25,000, our Store Manager will review and approve Refund #{payload['refund_id']} shortly (Ticket #{payload.get('escalation_ticket_id')})."
            )
        else:
            state.status = "pending_approval"
            payload_dict["action_feedback"] = {
                "type": "return_pending_approval",
                "badge": "VIP Concierge Review",
                "title": f"Return #{payload['return_id']} Logged for Executive Review",
                "summary": f"Orders over ₹25,000 receive Store Manager & Finance review (Ticket #{payload.get('escalation_ticket_id')}).",
                "cta_label": "Track Return Status",
                "cta_page": "orders",
            }
            state.reply = (
                f"I've logged your return (#{payload['return_id']}) for high-value Order #{payload['order_id']}. "
                f"Our Store Manager and Finance team are reviewing your refund under priority Ticket #{payload.get('escalation_ticket_id')}."
            )
        state.data = payload_dict
    elif code == 403:
        state.status = "blocked_unauthorized"
        state.data = payload_dict
        state.reply = payload_dict.get("message", "You do not have permission to return this order.")
    else:
        state.status = "answer"
        state.data = payload_dict
        state.reply = payload_dict.get("message", "This item isn't eligible for return under our return policy.")
    return state
