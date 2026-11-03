import re

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.refund_tools import SupportTools

ORDER_ID_RE = re.compile(r"\b(ORD-\d{4})\b", re.IGNORECASE)


def run_support_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = SupportTools(client)
    msg = state.request.message
    msg_lower = msg.lower()
    customer_id = state.request.customer_id or "CUS-001"

    ord_match = ORDER_ID_RE.search(msg)
    order_id = state.request.context.get("order_id") or (ord_match.group(1).upper() if ord_match else None)

    if "refund" in msg_lower and ("list" in msg_lower or "status" in msg_lower or "check" in msg_lower):
        code, payload = tools.list_refunds(
            order_id=order_id,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.status = "answer"
        state.data = {"refunds": payload if isinstance(payload, list) else []}
        if code == 200 and isinstance(payload, list) and payload:
            r0 = payload[0]
            state.reply = (
                f"Latest refund {r0['refund_id']} for order {r0['order_id']} (INR {r0['amount_inr']}, "
                f"Tier {r0['approval_tier']}) is currently '{r0['status']}'."
            )
        else:
            state.reply = "No refund records found."
        return state

    priority = "high" if any(k in msg_lower for k in ("urgent", "damaged", "conflict", "vip", "grievance")) else "medium"
    category = "exchange_request" if "exchange" in msg_lower else "concierge_escalation"

    code, tkt = tools.escalate_to_human(
        subject=f"Client Concierge Request ({order_id or customer_id})",
        description=msg,
        customer_id=customer_id,
        order_id=order_id,
        category=category,
        priority=priority,
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    state.data = tkt if isinstance(tkt, dict) else {}
    if code in (200, 201) and isinstance(tkt, dict):
        state.status = "escalated"
        state.reply = (
            f"I have created Noir Atelier Concierge Ticket {tkt['ticket_id']} "
            f"(Priority: {tkt['priority']}, Assigned to: {tkt['assigned_to']}). "
            f"Our specialist team will assist you promptly."
        )
    else:
        state.status = "error"
        state.reply = "Unable to create support ticket at this moment."
    return state
