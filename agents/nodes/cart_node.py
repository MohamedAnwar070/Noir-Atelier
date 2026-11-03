import re

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.cart_tools import CartTools

PRODUCT_ID_RE = re.compile(r"\b(PRD-\d{3})\b", re.IGNORECASE)
COUPON_RE = re.compile(r"\b(ATELIER10|SUMMER20|NOIR\d+)\b", re.IGNORECASE)
SIZE_RE = re.compile(r"\bsize\s+(XS|S|M|L|XL|4Y|6Y|8Y|10Y|12Y)\b", re.IGNORECASE)
QTY_RE = re.compile(r"\b(\d+)\s*(?:x|pcs?|pieces?|qty|quantity)\b", re.IGNORECASE)


def run_cart_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = CartTools(client)
    msg = state.request.message
    msg_lower = msg.lower()
    customer_id = state.request.customer_id or "CUS-001"
    session_id = state.request.session_id

    if "clear" in msg_lower and "cart" in msg_lower:
        code, payload = tools.clear_cart(
            customer_id=customer_id,
            session_id=session_id,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        state.status = "action_completed" if code == 200 else "error"
        state.data = payload if isinstance(payload, dict) else {"result": payload}
        state.reply = "Your Noir Atelier shopping bag has been cleared."
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
        state.data = res if isinstance(res, dict) else {}
        if code == 200 and isinstance(res, dict):
            state.reply = (
                f"Coupon {res['code']}: {res['message']} "
                f"(Discount: INR {res['discount_inr']}, New Total: INR {res['new_total_inr']})."
            )
        else:
            state.reply = f"Could not validate coupon {coupon_code}."
        return state

    prod_match = PRODUCT_ID_RE.search(msg)
    product_id = state.request.context.get("product_id") or (prod_match.group(1).upper() if prod_match else None)
    if ("add" in msg_lower or product_id) and "view" not in msg_lower and "show" not in msg_lower:
        target_prod = product_id or "PRD-001"
        size_m = SIZE_RE.search(msg)
        size = state.request.context.get("size") or (size_m.group(1).upper() if size_m else "M")
        qty_m = QTY_RE.search(msg)
        qty = int(state.request.context.get("quantity") or (qty_m.group(1) if qty_m else 1))

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
            state.data = cart
            state.reply = (
                f"Added {qty}x {target_prod} (Size {size}) to your bag. "
                f"Subtotal: INR {cart['subtotal_mrp_inr']} (incl. GST INR {cart['total_gst_inr']}), "
                f"Shipping: INR {cart['shipping_fee_inr']}, Grand Total: INR {cart['grand_total_inr']}."
            )
            return state

    code, cart = tools.get_cart(
        customer_id=customer_id,
        session_id=session_id,
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    state.status = "answer"
    state.data = cart if isinstance(cart, dict) else {}
    if code == 200 and isinstance(cart, dict):
        count = sum(i["quantity"] for i in cart.get("items", []))
        state.reply = (
            f"Your Noir Atelier bag has {count} garment(s). "
            f"Grand Total: INR {cart['grand_total_inr']} (Shipping: INR {cart['shipping_fee_inr']})."
        )
    else:
        state.reply = "Unable to retrieve cart summary."
    return state
