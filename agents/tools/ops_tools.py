from typing import Any, Dict, List, Optional, Tuple

from ..client import PlatformApiClient
from ..schemas.state import AgentRole, ToolCallTrace


class InventoryTools:
    """HTTP tool wrappers for inventory_agent (svc-inventory)."""

    def __init__(self, client: PlatformApiClient) -> None:
        self.client = client
        self.role = AgentRole.INVENTORY.value

    def list_inventory(
        self,
        *,
        low_stock_only: bool = False,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "list_inventory",
            "GET",
            "/api/inventory/list",
            params={"low_stock_only": low_stock_only},
            trace_id=trace_id,
            traces=traces,
        )

    def update_inventory(
        self,
        product_id: str,
        quantity_available: int,
        *,
        size_breakdown: Optional[Dict[str, int]] = None,
        reason: str = "agent_stock_adjustment",
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "update_inventory",
            "PUT",
            f"/api/inventory/{product_id}",
            trace_id=trace_id,
            json_body={
                "quantity_available": quantity_available,
                "size_breakdown": size_breakdown,
                "reason": reason,
            },
            traces=traces,
        )

    def discontinue_product(
        self,
        product_id: str,
        *,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "discontinue_product",
            "POST",
            f"/api/products/{product_id}/discontinue",
            trace_id=trace_id,
            traces=traces,
        )


class AnalyticsTools:
    """HTTP tool wrappers for analytics_agent (svc-analytics)."""

    def __init__(self, client: PlatformApiClient) -> None:
        self.client = client
        self.role = AgentRole.ANALYTICS.value

    def get_orders_analytics(
        self,
        *,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "get_orders_analytics",
            "GET",
            "/api/orders/analytics",
            trace_id=trace_id,
            traces=traces,
        )

    def get_customers_analytics(
        self,
        *,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "get_customers_analytics",
            "GET",
            "/api/customers/analytics",
            trace_id=trace_id,
            traces=traces,
        )

    def get_products_analytics(
        self,
        *,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "get_products_analytics",
            "GET",
            "/api/products/analytics",
            trace_id=trace_id,
            traces=traces,
        )


class ConfigTools:
    """HTTP tool wrappers for config_agent (svc-config)."""

    def __init__(self, client: PlatformApiClient) -> None:
        self.client = client
        self.role = AgentRole.CONFIG.value

    def get_policies_and_config(
        self,
        *,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "get_policies_and_config",
            "GET",
            "/api/config/policies",
            trace_id=trace_id,
            traces=traces,
        )

    def update_business_config(
        self,
        config_key: str,
        config_value: Dict[str, Any],
        *,
        reason: str = "config_agent_update",
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "update_business_config",
            "PUT",
            "/api/admin/config/policies",
            trace_id=trace_id,
            json_body={
                "config_key": config_key,
                "config_value": config_value,
                "reason": reason,
            },
            traces=traces,
        )

    def get_audit_log(
        self,
        *,
        limit: int = 25,
        resource_type: Optional[str] = None,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        params: Dict[str, Any] = {"limit": limit}
        if resource_type:
            params["resource_type"] = resource_type
        return self.client.call(
            self.role,
            "get_audit_log",
            "GET",
            "/api/audit/log",
            params=params,
            trace_id=trace_id,
            traces=traces,
        )
