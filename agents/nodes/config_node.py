from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.ops_tools import ConfigTools


def run_config_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = ConfigTools(client)
    msg_lower = state.request.message.lower()

    if "audit" in msg_lower:
        code, logs = tools.get_audit_log(
            limit=int(state.request.context.get("limit", 20)),
            resource_type=state.request.context.get("resource_type"),
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.status = "answer"
        state.data = {"audit_log": logs if isinstance(logs, list) else []}
        state.reply = (
            f"Retrieved {len(logs)} immutable audit log entries."
            if code == 200 and isinstance(logs, list)
            else "Unable to fetch audit logs."
        )
        return state

    if ("update" in msg_lower or "set" in msg_lower) and state.request.context.get("config_key"):
        key = str(state.request.context["config_key"])
        val = dict(state.request.context.get("config_value", {}))
        code, updated = tools.update_business_config(
            key,
            val,
            reason=state.request.context.get("reason", "config_agent_policy_update"),
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.data = updated if isinstance(updated, dict) else {}
        state.status = "action_completed" if code == 200 else "error"
        state.reply = (
            f"Updated business_config key '{key}' and invalidated cache."
            if code == 200
            else "Failed to update business configuration."
        )
        return state

    code, cfg = tools.get_policies_and_config(
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    state.status = "answer"
    state.data = cfg if isinstance(cfg, dict) else {}
    state.policy_citations.extend(["POL-RET-01", "POL-RET-02", "POL-VIP-01", "POL-CAN-01"])
    if code == 200 and isinstance(cfg, dict):
        bc = cfg.get("business_config", {})
        ret_cfg = bc.get("returns_and_refunds", {})
        tax_cfg = bc.get("tax", {})
        ship_cfg = bc.get("shipping", {})
        state.reply = (
            f"Noir Atelier Policies & Config: "
            f"{ret_cfg.get('return_window_days', 7)}-day return window from delivery with intact security ribbon "
            f"(POL-RET-01); Final Sale non-returnable (POL-RET-02); VIP Gold 14-day window (POL-VIP-01); "
            f"Pre-shipment cancellation auto-refunded (POL-CAN-01). "
            f"GST: 5% up to INR {tax_cfg.get('garment_slab_threshold_inr', 2500)}/pc, 18% above. "
            f"Free shipping on orders >= INR {ship_cfg.get('free_shipping_threshold_inr', 1999)}."
        )
    else:
        state.reply = "Unable to load business configuration."
    return state
