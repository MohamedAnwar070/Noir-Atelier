from typing import Any, Dict, List, Optional, Tuple

from ..client import PlatformApiClient
from ..schemas.state import AgentRole, ToolCallTrace


class CartTools:
    """HTTP tool wrappers for cart_agent (svc-cart)."""

    def __init__(self, client: PlatformApiClient) -> None:
        self.client = client
        self.role = AgentRole.CART.value

    def add_to_cart(
        self,
        *,
        product_id: str,
        size: str = "M",
        quantity: int = 1,
        customer_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "add_to_cart",
            "POST",
            "/api/cart/add",
            on_behalf_of=customer_id,
            trace_id=trace_id,
            json_body={
                "product_id": product_id,
                "size": size,
                "quantity": quantity,
                "customer_id": customer_id,
                "session_id": session_id,
            },
            traces=traces,
        )

    def get_cart(
        self,
        *,
        customer_id: Optional[str] = None,
        session_id: Optional[str] = None,
        coupon_code: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        params: Dict[str, Any] = {}
        if customer_id:
            params["customer_id"] = customer_id
        if session_id:
            params["session_id"] = session_id
        if coupon_code:
            params["coupon_code"] = coupon_code
        return self.client.call(
            self.role,
            "get_cart",
            "GET",
            "/api/cart",
            on_behalf_of=customer_id,
            params=params,
            trace_id=trace_id,
            traces=traces,
        )

    def remove_from_cart(
        self,
        item_id: str,
        *,
        customer_id: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "remove_from_cart",
            "DELETE",
            f"/api/cart/remove/{item_id}",
            on_behalf_of=customer_id,
            trace_id=trace_id,
            traces=traces,
        )

    def clear_cart(
        self,
        *,
        customer_id: Optional[str] = None,
        session_id: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        params: Dict[str, Any] = {}
        if customer_id:
            params["customer_id"] = customer_id
        if session_id:
            params["session_id"] = session_id
        return self.client.call(
            self.role,
            "clear_cart",
            "POST",
            "/api/cart/clear",
            on_behalf_of=customer_id,
            params=params,
            trace_id=trace_id,
            traces=traces,
        )

    def validate_coupon(
        self,
        code: str,
        cart_total_inr: float,
        *,
        customer_id: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "validate_coupon",
            "POST",
            "/api/coupons/validate",
            on_behalf_of=customer_id,
            trace_id=trace_id,
            json_body={"code": code, "cart_total_inr": cart_total_inr},
            traces=traces,
        )

    def calculate_order_preview(
        self,
        items: List[Dict[str, Any]],
        *,
        coupon_code: Optional[str] = None,
        destination_state: str = "Tamil Nadu",
        destination_pin: str = "600086",
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "calculate_order_preview",
            "POST",
            "/api/orders/calculate",
            trace_id=trace_id,
            json_body={
                "items": items,
                "coupon_code": coupon_code,
                "destination_state": destination_state,
                "destination_pin": destination_pin,
            },
            traces=traces,
        )
