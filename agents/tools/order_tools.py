from typing import Any, Dict, List, Optional, Tuple

from ..client import PlatformApiClient
from ..schemas.state import AgentRole, ToolCallTrace


class OrderTools:
    """HTTP tool wrappers for order_agent (svc-order)."""

    def __init__(self, client: PlatformApiClient) -> None:
        self.client = client
        self.role = AgentRole.ORDER.value

    def create_order(
        self,
        *,
        customer_id: str,
        items: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
        coupon_code: Optional[str] = None,
        payment_method: str = "upi",
        request_key: Optional[str] = None,
        estimated_amount_inr: Optional[float] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "create_order",
            "POST",
            "/api/orders",
            on_behalf_of=customer_id,
            trace_id=trace_id,
            amount_inr=estimated_amount_inr,
            json_body={
                "customer_id": customer_id,
                "session_id": session_id,
                "items": items,
                "coupon_code": coupon_code,
                "payment_method": payment_method,
                "request_key": request_key,
            },
            traces=traces,
        )

    def get_order_status(
        self,
        order_id: str,
        *,
        customer_id: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "get_order_status",
            "GET",
            f"/api/orders/{order_id}",
            on_behalf_of=customer_id,
            trace_id=trace_id,
            traces=traces,
        )

    def cancel_order(
        self,
        order_id: str,
        *,
        reason: str = "customer_requested_cancellation",
        customer_id: Optional[str] = None,
        request_key: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "cancel_order",
            "POST",
            f"/api/orders/{order_id}/cancel",
            on_behalf_of=customer_id,
            trace_id=trace_id,
            json_body={"reason": reason, "request_key": request_key},
            traces=traces,
        )

    def initiate_payment(
        self,
        order_id: str,
        *,
        method: str = "upi",
        customer_id: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "initiate_payment",
            "POST",
            "/api/payments/initiate",
            on_behalf_of=customer_id,
            trace_id=trace_id,
            json_body={"order_id": order_id, "method": method},
            traces=traces,
        )


class FulfillmentTools:
    """HTTP tool wrappers for fulfillment_agent (svc-fulfillment)."""

    def __init__(self, client: PlatformApiClient) -> None:
        self.client = client
        self.role = AgentRole.FULFILLMENT.value

    def get_shipment(
        self,
        identifier: str,
        *,
        customer_id: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "get_shipment",
            "GET",
            f"/api/shipments/{identifier}",
            on_behalf_of=customer_id,
            trace_id=trace_id,
            traces=traces,
        )

    def schedule_shipment(
        self,
        order_id: str,
        *,
        carrier: str = "Noir Express",
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "schedule_shipment",
            "POST",
            "/api/shipments/schedule",
            trace_id=trace_id,
            json_body={"order_id": order_id, "carrier": carrier},
            traces=traces,
        )
