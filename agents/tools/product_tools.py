from typing import Any, Dict, List, Optional, Tuple

from ..client import PlatformApiClient
from ..schemas.state import AgentRole, ToolCallTrace


class CatalogTools:
    """HTTP tool wrappers for catalog_agent (svc-catalog)."""

    def __init__(self, client: PlatformApiClient) -> None:
        self.client = client
        self.role = AgentRole.CATALOG.value

    def search_products(
        self,
        *,
        q: Optional[str] = None,
        category: Optional[str] = None,
        department: Optional[str] = None,
        max_price: Optional[float] = None,
        in_stock_only: bool = False,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        params: Dict[str, Any] = {"in_stock_only": in_stock_only}
        if q:
            params["q"] = q
        if category:
            params["category"] = category
        if department:
            params["department"] = department
        if max_price is not None:
            params["max_price"] = max_price

        return self.client.call(
            self.role,
            "search_products",
            "GET",
            "/api/products/search",
            params=params,
            trace_id=trace_id,
            traces=traces,
        )

    def get_product_details(
        self,
        product_id: str,
        *,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "get_product_details",
            "GET",
            f"/api/products/{product_id}",
            trace_id=trace_id,
            traces=traces,
        )

    def get_recommendations(
        self,
        product_id: str,
        *,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "get_recommendations",
            "GET",
            f"/api/products/{product_id}/recommendations",
            trace_id=trace_id,
            traces=traces,
        )

    def list_categories(
        self,
        *,
        trace_id: str = "TRC-000000",
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        return self.client.call(
            self.role,
            "list_categories",
            "GET",
            "/api/categories",
            trace_id=trace_id,
            traces=traces,
        )
