from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.ops_tools import ConfigTools
from .intent_parser import format_inr


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
            f"I found {len(logs)} recent activity log entries."
            if code == 200 and isinstance(logs, list)
            else "I couldn't load the activity log right now."
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
        updated_dict = dict(updated) if isinstance(updated, dict) else {}
        state.status = "action_completed" if code == 200 else "error"
        if code == 200:
            updated_dict["action_feedback"] = {
                "type": "config_updated",
                "badge": "Store Setting Updated",
                "title": f"Updated '{key}' Configuration",
                "summary": "Changes are now live across the storefront.",
            }
        state.data = updated_dict
        state.reply = (
            f"Done! I've updated the '{key}' store configuration."
            if code == 200
            else "I couldn't update that setting right now."
        )
        return state

    code, cfg = tools.get_policies_and_config(
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    state.status = "answer"
    cfg_dict = dict(cfg) if isinstance(cfg, dict) else {}
    state.policy_citations.extend(["POL-RET-01", "POL-RET-02", "POL-VIP-01", "POL-CAN-01"])
    if code == 200 and isinstance(cfg, dict):
        bc = cfg.get("business_config", {})
        ret_cfg = bc.get("returns_and_refunds", {})
        tax_cfg = bc.get("tax", {})
        ship_cfg = bc.get("shipping", {})
        win_days = ret_cfg.get("return_window_days", 7)
        vip_days = ret_cfg.get("vip_gold_return_window_days", 14)
        slab_inr = tax_cfg.get("garment_slab_threshold_inr", 2500)
        free_ship = ship_cfg.get("free_shipping_threshold_inr", 1999)
        cfg_dict["action_feedback"] = {
            "type": "policy_summary",
            "badge": "Atelier Care & Policies",
            "title": f"{win_days}-Day Returns · Free Shipping Over {format_inr(free_ship)}",
            "summary": f"5% GST on garments up to {format_inr(slab_inr)} · 18% GST above {format_inr(slab_inr)}.",
            "cta_label": "Read Full Atelier Policies",
            "cta_page": "policies",
        }
        state.data = cfg_dict
        state.reply = (
            f"Here is a quick summary of our Noir Atelier policies:\n"
            f"• Easy Returns: {win_days}-day return window from delivery ({vip_days} days for VIP Gold members) as long as the garment is unworn with the security ribbon intact.\n"
            f"• Instant Pre-Shipment Cancellation: Cancel any time before dispatch for an immediate full refund.\n"
            f"• Transparent GST: 5% GST on garments priced up to {format_inr(slab_inr)} per piece, and 18% GST above {format_inr(slab_inr)}.\n"
            f"• Complimentary Delivery: Free shipping on all orders of {format_inr(free_ship)} or more."
        )
    else:
        state.data = cfg_dict
        state.reply = "I couldn't load the store policies right now."
    return state
