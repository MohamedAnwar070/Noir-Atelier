from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.ops_tools import AnalyticsTools


def run_analytics_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = AnalyticsTools(client)
    msg_lower = state.request.message.lower()

    if "customer" in msg_lower or "retention" in msg_lower or "loyalty" in msg_lower:
        code, cust_stats = tools.get_customers_analytics(
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.status = "answer"
        state.data = {"customers_analytics": cust_stats if isinstance(cust_stats, dict) else {}}
        if code == 200 and isinstance(cust_stats, dict):
            state.reply = (
                f"Customer Analytics: {cust_stats['total_customers']} registered clients, "
                f"{cust_stats['repeat_buyers']} repeat buyers ({cust_stats['retention_rate_pct']}% retention)."
            )
        else:
            state.reply = "Unable to fetch customer analytics."
        return state

    if "product" in msg_lower or "sku" in msg_lower or "velocity" in msg_lower:
        code, prod_stats = tools.get_products_analytics(
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.status = "answer"
        state.data = {"products_analytics": prod_stats if isinstance(prod_stats, dict) else {}}
        if code == 200 and isinstance(prod_stats, dict):
            inv_count = len(prod_stats.get("inventory", []))
            rev = prod_stats.get("sales", {}).get("total_revenue_inr", 0)
            state.reply = f"Product Analytics: {inv_count} active garment SKUs tracked; cumulative revenue INR {rev}."
        else:
            state.reply = "Unable to fetch product analytics."
        return state

    code, ord_stats = tools.get_orders_analytics(
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    state.status = "answer"
    state.data = {"orders_analytics": ord_stats if isinstance(ord_stats, dict) else {}}
    if code == 200 and isinstance(ord_stats, dict):
        state.reply = (
            f"Order Analytics: {ord_stats['total_orders']} total orders, "
            f"Total Revenue INR {ord_stats['total_revenue_inr']}."
        )
    else:
        state.reply = "Unable to fetch order analytics."
    return state
