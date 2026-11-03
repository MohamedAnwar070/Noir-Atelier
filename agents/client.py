import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from .gateway import ToolPolicyGate, ToolPolicyGateError, classify_endpoint_risk
from .schemas.state import ToolCallTrace


class PlatformApiClient:
    """Scoped HTTP client for agents calling /api/* endpoints with zero direct DB access."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        in_process_client: Optional[Any] = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("BACKEND_API_URL", "http://localhost:8000")).rstrip("/")
        self._in_process_client = in_process_client
        self.timeout_seconds = timeout_seconds

    def _get_in_process_client(self) -> Any:
        if self._in_process_client is None:
            from fastapi.testclient import TestClient
            from backend.app.main import app

            self._in_process_client = TestClient(app)
        return self._in_process_client

    def call(
        self,
        agent_role: str,
        tool_name: str,
        method: str,
        endpoint: str,
        *,
        on_behalf_of: Optional[str] = None,
        trace_id: str = "TRC-000000",
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        amount_inr: Optional[float] = None,
        override_token: Optional[str] = None,
        traces: Optional[List[ToolCallTrace]] = None,
    ) -> Tuple[int, Any]:
        t0 = time.perf_counter()
        try:
            service_account = ToolPolicyGate.verify_call(
                agent_role=agent_role,
                method=method,
                endpoint=endpoint,
                amount_inr=amount_inr,
            )
        except ToolPolicyGateError as exc:
            latency = round((time.perf_counter() - t0) * 1000, 2)
            if traces is not None:
                traces.append(
                    ToolCallTrace(
                        agent_name=agent_role,
                        service_account=override_token or "blocked",
                        tool_name=tool_name,
                        http_method=method.upper(),
                        endpoint=endpoint,
                        risk_level=classify_endpoint_risk(method, endpoint),
                        status_code=403,
                        latency_ms=latency,
                        allowed_by_gate=False,
                        error=exc.message,
                    )
                )
            return 403, {"code": exc.code, "message": exc.message}

        bearer_token = override_token or service_account
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {bearer_token}",
            "X-Trace-Id": trace_id,
        }
        if on_behalf_of:
            headers["X-On-Behalf-Of"] = on_behalf_of

        status_code: int
        payload: Any

        use_in_process = (
            self._in_process_client is not None
            or os.getenv("AGENT_HTTP_TRANSPORT", "in_process").lower() == "in_process"
        )

        if use_in_process:
            client = self._get_in_process_client()
            resp = client.request(
                method=method.upper(),
                url=endpoint,
                params=params,
                json=json_body,
                headers=headers,
            )
            status_code = resp.status_code
            try:
                payload = resp.json()
            except Exception:
                payload = {"raw": resp.text}
        else:
            with httpx.Client(base_url=self.base_url, timeout=self.timeout_seconds) as http:
                resp = http.request(
                    method=method.upper(),
                    url=endpoint,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
                status_code = resp.status_code
                try:
                    payload = resp.json()
                except Exception:
                    payload = {"raw": resp.text}

        latency = round((time.perf_counter() - t0) * 1000, 2)
        if traces is not None:
            summary: Dict[str, Any] = {}
            if isinstance(payload, list):
                summary["count"] = len(payload)
            elif isinstance(payload, dict):
                for key in ("order_id", "return_id", "refund_id", "shipment_id", "ticket_id", "product_id", "status", "code"):
                    if key in payload:
                        summary[key] = payload[key]
            traces.append(
                ToolCallTrace(
                    agent_name=agent_role,
                    service_account=bearer_token,
                    tool_name=tool_name,
                    http_method=method.upper(),
                    endpoint=endpoint,
                    risk_level=classify_endpoint_risk(method, endpoint),
                    status_code=status_code,
                    latency_ms=latency,
                    allowed_by_gate=True,
                    error=payload.get("message") if status_code >= 400 and isinstance(payload, dict) else None,
                    summary=summary,
                )
            )
        return status_code, payload
