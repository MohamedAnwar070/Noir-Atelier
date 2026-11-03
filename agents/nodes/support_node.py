import re

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.refund_tools import SupportTools
from .intent_parser import format_inr

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
        refund_list = payload if isinstance(payload, list) else []
        state.data = {"refunds": refund_list}
        if code == 200 and refund_list:
            r0 = refund_list[0]
            state.data["action_feedback"] = {
                "type": "refund_status",
                "badge": f"Refund: {str(r0['status']).replace('_', ' ').title()}",
                "title": f"Refund #{r0['refund_id']} ({format_inr(r0['amount_inr'])})",
                "summary": f"Order #{r0['order_id']} · Status: {str(r0['status']).replace('_', ' ')}",
            }
            state.reply = (
                f"Your latest refund (#{r0['refund_id']}) for Order #{r0['order_id']} ({format_inr(r0['amount_inr'])}) "
                f"is currently {str(r0['status']).replace('_', ' ')}."
            )
        else:
            state.reply = "No refund requests were found for your account."
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
    tkt_dict = dict(tkt) if isinstance(tkt, dict) else {}
    if code in (200, 201) and isinstance(tkt, dict):
        state.status = "escalated"
        tkt_dict["action_feedback"] = {
            "type": "support_ticket_created",
            "badge": "Concierge Ticket Created",
            "title": f"Support Ticket #{tkt['ticket_id']} Opened",
            "summary": f"Assigned to {tkt['assigned_to']} ({str(tkt['priority']).title()} Priority)",
            "details": [
                {"label": "Ticket Number", "value": tkt["ticket_id"]},
                {"label": "Priority", "value": str(tkt["priority"]).title()},
                {"label": "Assigned Specialist", "value": tkt["assigned_to"]},
            ],
        }
        state.data = tkt_dict
        state.reply = (
            f"I've connected your request to our human Concierge team under Ticket #{tkt['ticket_id']} "
            f"({tkt['priority']} priority, assigned to {tkt['assigned_to']}). Our team will follow up with you shortly."
        )
    else:
        state.status = "error"
        state.data = tkt_dict
        state.reply = "I wasn't able to open a support ticket right now."
    return state
