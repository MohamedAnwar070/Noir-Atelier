from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.ops_tools import AnalyticsTools
from .intent_parser import format_inr


def run_analytics_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = AnalyticsTools(client)
    msg_lower = state.request.message.lower()

    if "customer" in msg_lower or "retention" in msg_lower or "loyalty" in msg_lower:
        code, cust_stats = tools.get_customers_analytics(
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.status = "answer"
        stats_dict = dict(cust_stats) if isinstance(cust_stats, dict) else {}
        state.data = {"customers_analytics": stats_dict}
        if code == 200 and isinstance(cust_stats, dict):
            state.data["action_feedback"] = {
                "type": "analytics_report",
                "badge": "Client Insights",
                "title": f"{cust_stats['total_customers']} Active Clients · {cust_stats['retention_rate_pct']}% Retention",
                "summary": f"{cust_stats['repeat_buyers']} repeat buyers recorded.",
            }
            state.reply = (
                f"Here is our latest client overview:\n"
                f"• Registered Clients: {cust_stats['total_customers']}\n"
                f"• Repeat Buyers: {cust_stats['repeat_buyers']} ({cust_stats['retention_rate_pct']}% retention rate)"
            )
        else:
            state.reply = "I couldn't load customer analytics right now."
        return state

    if "product" in msg_lower or "sku" in msg_lower or "velocity" in msg_lower:
        code, prod_stats = tools.get_products_analytics(
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.status = "answer"
        stats_dict = dict(prod_stats) if isinstance(prod_stats, dict) else {}
        state.data = {"products_analytics": stats_dict}
        if code == 200 and isinstance(prod_stats, dict):
            inv_count = len(prod_stats.get("inventory", []))
            rev = prod_stats.get("sales", {}).get("total_revenue_inr", 0)
            state.data["action_feedback"] = {
                "type": "analytics_report",
                "badge": "Collection Performance",
                "title": f"{inv_count} Garments Tracked · {format_inr(rev)} Revenue",
                "summary": "Live stock and sales performance across Men, Women & Kids.",
            }
            state.reply = (
                f"We are currently tracking {inv_count} active garments with {format_inr(rev)} in total sales."
            )
        else:
            state.reply = "I couldn't load product performance right now."
        return state

    code, ord_stats = tools.get_orders_analytics(
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    state.status = "answer"
    stats_dict = dict(ord_stats) if isinstance(ord_stats, dict) else {}
    state.data = {"orders_analytics": stats_dict}
    if code == 200 and isinstance(ord_stats, dict):
        top_prods = ord_stats.get("top_products", [])
        top_line = (
            f"\n• Best Seller: {top_prods[0]['product_name']} ({top_prods[0]['units_sold']} sold)"
            if top_prods
            else ""
        )
        state.data["action_feedback"] = {
            "type": "analytics_report",
            "badge": "Store Revenue Snapshot",
            "title": f"{ord_stats['total_orders']} Orders · {format_inr(ord_stats['total_revenue_inr'])} Total Revenue",
            "summary": top_prods[0]["product_name"] + " leads sales." if top_prods else "Live revenue from confirmed orders.",
        }
        state.reply = (
            f"Here is the live Noir Atelier sales summary:\n"
            f"• Confirmed Orders: {ord_stats['total_orders']}\n"
            f"• Total Revenue (GMV): {format_inr(ord_stats['total_revenue_inr'])}"
            + top_line
        )
    else:
        state.reply = "I couldn't load the sales report right now."
    return state
