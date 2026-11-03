from typing import Any, Dict, List, Optional, Tuple

from ..client import PlatformApiClient
from ..schemas.state import AgentRole, ToolCallTrace


class ReturnsTools:
    """HTTP tool wrappers for returns_agent (svc-returns)."""

    def __init__(self, client: PlatformApiClient) -> None:
        self.client = client
        self.role = AgentRole.RETURNS.value

    def initiate_return(
        self,
        order_id: str,
        *,
        reason_category: str = "size_mismatch",
        customer_notes: Optional[str] = None,
        tag_intact: bool = True,
        qc_passed: bool = True,
        is_defective_claim: bool = False,
        customer_id: Optional[str] = None,
        request_key: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "initiate_return",
            "POST",
            "/api/returns",
            on_behalf_of=customer_id,
            trace_id=trace_id,
            json_body={
                "order_id": order_id,
                "reason_category": reason_category,
                "customer_notes": customer_notes,
                "tag_intact": tag_intact,
                "qc_passed": qc_passed,
                "is_defective_claim": is_defective_claim,
                "request_key": request_key,
            },
            traces=traces,
        )

    def get_return_status(
        self,
        return_id: str,
        *,
        customer_id: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "get_return_status",
            "GET",
            f"/api/returns/{return_id}",
            on_behalf_of=customer_id,
            trace_id=trace_id,
            traces=traces,
        )

    def approve_refund(
        self,
        refund_id: str,
        *,
        reason: str = "policy_verified_qc_passed",
        override_token: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "approve_refund",
            "POST",
            f"/api/refunds/{refund_id}/approve",
            override_token=override_token,
            trace_id=trace_id,
            json_body={"reason": reason},
            traces=traces,
        )

    def process_refund(
        self,
        refund_id: str,
        *,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "process_refund",
            "POST",
            f"/api/refunds/{refund_id}/process",
            trace_id=trace_id,
            traces=traces,
        )

    def restock_inventory(
        self,
        product_id: str,
        quantity: int = 1,
        *,
        size: str = "M",
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "restock_inventory",
            "POST",
            "/api/inventory/restock",
            trace_id=trace_id,
            json_body={"product_id": product_id, "size": size, "quantity": quantity},
            traces=traces,
        )


class SupportTools:
    """HTTP tool wrappers for support_agent (svc-support)."""

    def __init__(self, client: PlatformApiClient) -> None:
        self.client = client
        self.role = AgentRole.SUPPORT.value

    def get_order_details(
        self,
        order_id: str,
        *,
        customer_id: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "get_order_details",
            "GET",
            f"/api/orders/{order_id}",
            on_behalf_of=customer_id,
            trace_id=trace_id,
            traces=traces,
        )

    def list_refunds(
        self,
        *,
        order_id: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        params = {"order_id": order_id} if order_id else None
        return self.client.call(
            self.role,
            "list_refunds",
            "GET",
            "/api/refunds",
            params=params,
            trace_id=trace_id,
            traces=traces,
        )

    def escalate_to_human(
        self,
        *,
        subject: str,
        description: str,
        customer_id: Optional[str] = None,
        order_id: Optional[str] = None,
        category: str = "general",
        priority: str = "medium",
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "escalate_to_human",
            "POST",
            "/api/support/escalate",
            on_behalf_of=customer_id,
            trace_id=trace_id,
            json_body={
                "customer_id": customer_id,
                "order_id": order_id,
                "subject": subject,
                "description": description,
                "category": category,
                "priority": priority,
            },
            traces=traces,
        )
