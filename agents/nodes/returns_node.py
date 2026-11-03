import re

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.refund_tools import ReturnsTools

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
            state.data = payload if isinstance(payload, dict) else {}
            state.status = "action_completed" if code == 200 else "error"
            state.reply = (
                f"Refund {refund_id} processed (Payment Ref: {payload.get('payment_refund_id')})."
                if code == 200 and isinstance(payload, dict)
                else payload.get("message", "Could not process refund.")
            )
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
        state.data = payload if isinstance(payload, dict) else {}
        if code == 200 and isinstance(payload, dict):
            state.status = "action_completed" if payload["status"] == "approved" else "pending_approval"
            state.reply = (
                f"Refund {payload['refund_id']} (Tier {payload['approval_tier']}) status is now '{payload['status']}'."
            )
        elif code == 403:
            state.status = "blocked_unauthorized"
            state.reply = payload.get("message", "Refund approval requires elevated manager/finance privileges.")
        else:
            state.status = "error"
            state.reply = payload.get("message", "Could not approve refund.")
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
        state.data = payload if isinstance(payload, dict) else {}
        state.status = "answer"
        if code == 200 and isinstance(payload, dict):
            state.reply = (
                f"Return {payload['return_id']} for {payload['order_id']} is '{payload['status']}' "
                f"(Tier {payload['approval_tier']}, Refund: {payload['refund_id']} [{payload['refund_status']}])."
            )
        else:
            state.reply = payload.get("message", f"Return {return_id} not found.")
        return state

    ord_match = ORDER_ID_RE.search(msg)
    order_id = state.request.context.get("order_id") or (ord_match.group(1).upper() if ord_match else None)
    if not order_id:
        state.status = "clarify_missing_info"
        state.reply = "Please share your Noir Atelier order ID (e.g., ORD-1001) and return reason so I can initiate your garment return."
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
    state.data = payload if isinstance(payload, dict) else {}
    state.policy_citations.extend(["POL-RET-01", "POL-RET-02"])

    if code in (200, 201) and isinstance(payload, dict):
        tier = payload.get("approval_tier", 1)
        if tier == 1:
            state.status = "action_completed"
            state.reply = (
                f"Return {payload['return_id']} for {payload['order_id']} passed Tier 1 QC & security ribbon check "
                f"(POL-RET-01). Refund {payload['refund_id']} has been auto-approved and processed!"
            )
        elif tier == 2:
            state.status = "pending_approval"
            state.reply = (
                f"Return {payload['return_id']} for luxury garment order {payload['order_id']} is logged under "
                f"Tier 2 (INR 5,001–25,000) and escalated to a Store Manager via ticket {payload.get('escalation_ticket_id')}."
            )
        else:
            state.status = "pending_approval"
            state.reply = (
                f"Return {payload['return_id']} for high-value order {payload['order_id']} is logged under "
                f"Tier 3 (> INR 25,000) requiring dual Store Manager + Finance Admin approval "
                f"(Ticket: {payload.get('escalation_ticket_id')})."
            )
    elif code == 403:
        state.status = "blocked_unauthorized"
        state.reply = payload.get("message", "You are not authorized to return this order.")
    else:
        state.status = "answer"
        state.reply = payload.get("message", "Return request could not be completed under Noir Atelier policy.")
    return state
