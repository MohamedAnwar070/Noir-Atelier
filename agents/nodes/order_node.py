import re

from ..client import PlatformApiClient
from ..schemas.state import AgentGraphState
from ..tools.order_tools import OrderTools
from .intent_parser import (
    extract_quantity,
    extract_size,
    format_inr,
    resolve_product_from_message,
)

ORDER_ID_RE = re.compile(r"\b(ORD-\d{4})\b", re.IGNORECASE)


def run_order_node(state: AgentGraphState, client: PlatformApiClient) -> AgentGraphState:
    tools = OrderTools(client)
    msg = state.request.message
    msg_lower = msg.lower()
    customer_id = state.request.customer_id or "CUS-001"

    ord_match = ORDER_ID_RE.search(msg)
    order_id = state.request.context.get("order_id") or (ord_match.group(1).upper() if ord_match else None)

    if "cancel" in msg_lower:
        if not order_id:
            state.status = "clarify_missing_info"
            state.reply = (
                "I can cancel your order right away! Please share your Order ID (for example, ORD-1001)."
            )
            return state

        code, payload = tools.cancel_order(
            order_id,
            reason=state.request.context.get("reason", "customer_requested_cancellation"),
            customer_id=customer_id,
            request_key=state.request.request_key,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        payload_dict = dict(payload) if isinstance(payload, dict) else {}
        state.policy_citations.append("POL-CAN-01")
        if code == 200 and isinstance(payload, dict):
            state.status = "action_completed"
            payload_dict["action_feedback"] = {
                "type": "order_cancelled",
                "badge": "Order Cancelled & Refunded",
                "title": f"Order #{payload['order_id']} Cancelled",
                "summary": f"Full refund of {format_inr(payload.get('grand_total_inr', 0))} has been processed.",
                "details": [
                    {"label": "Order ID", "value": payload["order_id"]},
                    {"label": "Status", "value": "Cancelled"},
                    {"label": "Refund Amount", "value": format_inr(payload.get("grand_total_inr", 0))},
                ],
                "cta_label": "View Orders & Returns",
                "cta_page": "orders",
            }
            state.data = payload_dict
            state.reply = (
                f"Done! Your Order #{payload['order_id']} has been cancelled before shipment, "
                f"and your full refund of {format_inr(payload.get('grand_total_inr', 0))} has been processed."
            )
        elif code == 403:
            state.status = "blocked_unauthorized"
            state.data = payload_dict
            state.reply = payload.get("message", "You do not have permission to cancel this order.")
        else:
            state.status = "answer"
            state.data = payload_dict
            state.reply = payload.get("message", f"Order {order_id} can no longer be cancelled because it has already been shipped.")
        return state

    if any(k in msg_lower for k in ("place order", "buy", "checkout", "create order", "purchase")):
        items = state.request.context.get("items")
        if not items:
            resolved_prod, all_prods = resolve_product_from_message(msg, state.request.context, client)
            if resolved_prod is None and msg_lower.strip() in ("buy", "i want to buy", "place order", "purchase"):
                state.status = "clarify_missing_info"
                names = [f"• {p['name']} ({format_inr(p['mrp_inr'])})" for p in all_prods[:5]]
                state.data = {
                    "products": all_prods,
                    "action_feedback": {
                        "type": "choose_garment",
                        "badge": "Select a Garment",
                        "title": "Which piece would you like to order?",
                        "summary": "Pick any garment below or tell me the name and quantity (e.g., 'Buy 2 Minimalist Pima Cotton Tee').",
                    },
                }
                state.reply = (
                    "I'd be happy to place your order! Which piece would you like to buy?\n"
                    + "\n".join(names)
                    + "\n\nJust tell me the name, size, and quantity — or click Buy Now on any card below."
                )
                return state

            target = resolved_prod or (all_prods[0] if all_prods else {"product_id": "PRD-001", "sizes_available": ["M"]})
            pid = target.get("product_id", "PRD-001")
            avail_sizes = target.get("sizes_available") or ["M"]
            size = extract_size(msg, state.request.context, avail_sizes)
            qty = extract_quantity(msg, state.request.context)
            items = [{"product_id": pid, "size": size, "quantity": qty}]

        estimated = state.request.context.get("estimated_amount_inr")
        code, payload = tools.create_order(
            customer_id=customer_id,
            items=items,
            session_id=state.request.session_id,
            coupon_code=state.request.context.get("coupon_code"),
            payment_method=state.request.context.get("payment_method", "upi"),
            request_key=state.request.request_key,
            estimated_amount_inr=float(estimated) if estimated is not None else None,
            trace_id=state.trace_id,
            traces=state.tool_traces,
        )
        payload_dict = dict(payload) if isinstance(payload, dict) else {}
        if code in (200, 201) and isinstance(payload, dict):
            state.status = "action_completed"
            order_items = payload.get("items", [])
            item_summary = ", ".join(
                f"{it['quantity']} × {it['product_name']} (Size {it['size']})" for it in order_items
            ) or "Your selected garment(s)"
            shipping_label = (
                "Free Shipping"
                if float(payload.get("shipping_fee_inr", 0)) == 0
                else format_inr(payload.get("shipping_fee_inr", 0))
            )
            details_list = [
                {"label": "Order Number", "value": payload["order_id"]},
                {"label": "Items Ordered", "value": item_summary},
                {"label": "Subtotal", "value": format_inr(payload.get("subtotal_mrp_inr", 0))},
                {"label": "Included GST", "value": format_inr(payload.get("total_gst_inr", 0))},
                {"label": "Delivery", "value": shipping_label},
                {"label": "Total Paid", "value": format_inr(payload.get("grand_total_inr", 0))},
            ]
            if payload.get("invoice_id"):
                details_list.append({"label": "Tax Invoice", "value": payload["invoice_id"]})
            if payload.get("locker_number") and payload.get("pickup_code"):
                details_list.append(
                    {"label": "Boutique Pickup", "value": f"Locker #{payload['locker_number']} · Code {payload['pickup_code']}"}
                )

            payload_dict["action_feedback"] = {
                "type": "order_created",
                "badge": "Order Confirmed & Paid",
                "title": f"Order #{payload['order_id']} Placed Successfully",
                "summary": f"{item_summary} · Total Paid {format_inr(payload['grand_total_inr'])}",
                "details": details_list,
                "cta_label": "View My Order & Invoice",
                "cta_page": "orders",
            }
            state.data = payload_dict
            state.reply = (
                f"Your order is confirmed! I've placed Order #{payload['order_id']} for {item_summary}.\n\n"
                f"• Total Paid: {format_inr(payload['grand_total_inr'])} (includes {format_inr(payload['total_gst_inr'])} GST & {shipping_label})\n"
                f"• Invoice Number: {payload.get('invoice_id', 'Generated')}\n"
                + (
                    f"• Boutique Locker Pickup: Locker #{payload['locker_number']} (Pickup Code: {payload['pickup_code']})"
                    if payload.get("locker_number")
                    else ""
                )
            ).strip()
        elif code == 403:
            state.status = "blocked_unauthorized"
            state.data = payload_dict
            state.reply = payload.get("message", "This order exceeds the automated spending limit and needs review.")
        else:
            state.status = "error"
            state.data = payload_dict
            state.reply = payload.get("message", "I wasn't able to complete your order right now.")
        return state

    if not order_id:
        state.status = "clarify_missing_info"
        state.reply = "Please share your Order ID (for example, ORD-1001) so I can check its status for you."
        return state

    code, payload = tools.get_order_status(
        order_id,
        customer_id=customer_id,
        trace_id=state.trace_id,
        traces=state.tool_traces,
    )
    payload_dict = dict(payload) if isinstance(payload, dict) else {}
    if code == 200 and isinstance(payload, dict):
        state.status = "answer"
        item_summary = ", ".join(
            f"{it['quantity']} × {it['product_name']} (Size {it['size']})" for it in payload.get("items", [])
        )
        payload_dict["action_feedback"] = {
            "type": "order_status",
            "badge": f"Status: {str(payload['status']).replace('_', ' ').title()}",
            "title": f"Order #{payload['order_id']}",
            "summary": f"{item_summary} · Total {format_inr(payload['grand_total_inr'])}",
            "cta_label": "View in Orders",
            "cta_page": "orders",
        }
        state.data = payload_dict
        state.reply = (
            f"Order #{payload['order_id']} is currently {str(payload['status']).replace('_', ' ')} "
            f"(Payment: {payload['payment_status']}, Total: {format_inr(payload['grand_total_inr'])})."
        )
    elif code == 403:
        state.status = "blocked_unauthorized"
        state.data = payload_dict
        state.reply = payload.get("message", "You do not have access to this order.")
    else:
        state.status = "answer"
        state.data = payload_dict
        state.reply = payload.get("message", f"I couldn't find an order with ID {order_id}.")
    return state
