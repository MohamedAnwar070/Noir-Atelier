import re

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.cart_tools import CartTools
from .intent_parser import (
    extract_quantity,
    extract_size,
    format_inr,
    resolve_product_from_message,
)

COUPON_RE = re.compile(r"\b(ATELIER10|SUMMER20|NOIR\d+)\b", re.IGNORECASE)


def run_cart_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = CartTools(client)
    msg = state.request.message
    msg_lower = msg.lower()
    customer_id = state.request.customer_id or "CUS-001"
    session_id = state.request.session_id

    if "clear" in msg_lower and ("cart" in msg_lower or "bag" in msg_lower):
        code, payload = tools.clear_cart(
            customer_id=customer_id,
            session_id=session_id,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.status = "action_completed" if code == 200 else "error"
        data_dict = payload if isinstance(payload, dict) else {"result": payload}
        data_dict["action_feedback"] = {
            "type": "cart_cleared",
            "badge": "Shopping Bag Cleared",
            "title": "Your Shopping Bag is Now Empty",
            "summary": "All items have been removed from your shopping bag.",
        }
        state.data = data_dict
        state.reply = "Done! I've cleared all items from your shopping bag."
        return state

    coupon_match = COUPON_RE.search(msg)
    if "coupon" in msg_lower or "promo" in msg_lower or coupon_match:
        coupon_code = (
            state.request.context.get("coupon_code")
            or (coupon_match.group(1).upper() if coupon_match else "ATELIER10")
        )
        cart_total = float(state.request.context.get("cart_total_inr", 2499.0))
        code, res = tools.validate_coupon(
            coupon_code,
            cart_total,
            customer_id=customer_id,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.status = "answer"
        res_dict = dict(res) if isinstance(res, dict) else {}
        if code == 200 and isinstance(res, dict):
            res_dict["action_feedback"] = {
                "type": "coupon_validated",
                "badge": "Promo Code Applied" if res.get("valid") else "Promo Code Notice",
                "title": f"Code {res['code']} — Save {format_inr(res.get('discount_inr', 0))}",
                "summary": f"Updated Total: {format_inr(res.get('new_total_inr', cart_total))}",
                "cta_label": "Open Shopping Bag",
                "cta_drawer": "bag",
            }
            state.data = res_dict
            state.reply = (
                f"Great news — promo code {res['code']} is valid! "
                f"You save {format_inr(res['discount_inr'])}, bringing your total to {format_inr(res['new_total_inr'])}."
                if res.get("valid")
                else f"Promo code {res['code']} couldn't be applied: {res.get('message', '')}"
            )
        else:
            state.data = res_dict
            state.reply = f"I couldn't apply promo code {coupon_code} right now."
        return state

    resolved_prod, _ = resolve_product_from_message(msg, state.request.context, client)
    if ("add" in msg_lower or resolved_prod is not None) and "view" not in msg_lower and "show" not in msg_lower:
        target_prod = (resolved_prod or {}).get("product_id") or "PRD-001"
        prod_name = (resolved_prod or {}).get("name") or target_prod
        avail_sizes = (resolved_prod or {}).get("sizes_available") or ["M"]
        size = extract_size(msg, state.request.context, avail_sizes)
        qty = extract_quantity(msg, state.request.context)

        code, cart = tools.add_to_cart(
            product_id=target_prod,
            size=size,
            quantity=qty,
            customer_id=customer_id,
            session_id=session_id,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        if code == 200 and isinstance(cart, dict):
            state.status = "action_completed"
            cart_copy = dict(cart)
            total_items = sum(int(i.get("quantity", 0)) for i in cart.get("items", []))
            shipping_txt = (
                "Free Shipping"
                if float(cart.get("shipping_fee_inr", 0)) == 0
                else f"Shipping {format_inr(cart['shipping_fee_inr'])}"
            )
            cart_copy["action_feedback"] = {
                "type": "cart_updated",
                "badge": "Added to Shopping Bag",
                "title": f"Added {qty} × {prod_name} (Size {size})",
                "summary": f"Bag now has {total_items} item(s) · Total {format_inr(cart['grand_total_inr'])} ({shipping_txt})",
                "details": [
                    {"label": "Garment", "value": f"{qty} × {prod_name} (Size {size})"},
                    {"label": "Bag Subtotal", "value": format_inr(cart["subtotal_mrp_inr"])},
                    {"label": "Included GST", "value": format_inr(cart["total_gst_inr"])},
                    {"label": "Bag Total", "value": format_inr(cart["grand_total_inr"])},
                ],
                "cta_label": "View Shopping Bag & Checkout",
                "cta_drawer": "bag",
            }
            state.data = cart_copy
            state.reply = (
                f"Done! I've added {qty} × {prod_name} (Size {size}) to your shopping bag.\n\n"
                f"• Items in Bag: {total_items}\n"
                f"• Bag Total: {format_inr(cart['grand_total_inr'])} (includes {format_inr(cart['total_gst_inr'])} GST · {shipping_txt})"
            )
            return state

    code, cart = tools.get_cart(
        customer_id=customer_id,
        session_id=session_id,
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    state.status = "answer"
    cart_dict = dict(cart) if isinstance(cart, dict) else {}
    if code == 200 and isinstance(cart, dict):
        count = sum(i["quantity"] for i in cart.get("items", []))
        cart_dict["action_feedback"] = {
            "type": "cart_summary",
            "badge": f"{count} Item(s) in Bag",
            "title": f"Bag Total: {format_inr(cart.get('grand_total_inr', 0))}",
            "summary": "Ready for checkout whenever you are.",
            "cta_label": "Open Shopping Bag",
            "cta_drawer": "bag",
        }
        state.data = cart_dict
        if count == 0:
            state.reply = "Your shopping bag is currently empty. Tell me which piece you'd like to add!"
        else:
            item_lines = [
                f"• {i['quantity']} × {i['product_name']} (Size {i['size']}) — {format_inr(i['line_mrp_inr'])}"
                for i in cart.get("items", [])
            ]
            state.reply = (
                f"You have {count} item(s) in your shopping bag:\n"
                + "\n".join(item_lines)
                + f"\n\nTotal: {format_inr(cart['grand_total_inr'])} (Shipping: {format_inr(cart['shipping_fee_inr'])})."
            )
    else:
        state.data = cart_dict
        state.reply = "I couldn't load your shopping bag right now."
    return state
