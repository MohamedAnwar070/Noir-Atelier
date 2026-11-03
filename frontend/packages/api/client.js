export class NoirApiClient {
  constructor({ baseUrl = "", slowThresholdMs = 1200, onNetworkEvent = null } = {}) {
    this.baseUrl =
      baseUrl ||
      (typeof window !== "undefined" && window.NOIR_API_BASE) ||
      "http://127.0.0.1:8000";
    this.token = "demo_CUS-001";
    this.slowThresholdMs = slowThresholdMs;
    this.onNetworkEvent = onNetworkEvent;
  }

  setToken(token) {
    this.token = token;
  }

  async request(method, path, { params = null, body = null, tokenOverride = null } = {}) {
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      this.onNetworkEvent?.({ type: "offline" });
      throw {
        status: 0,
        code: "offline",
        message: "Browser reports no active internet connection.",
        trace_id: "TRC-OFFLINE",
      };
    }

    const url = new URL(path, this.baseUrl);
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== "") {
          url.searchParams.set(k, String(v));
        }
      });
    }

    const headers = {
      "Content-Type": "application/json",
      Authorization: `Bearer ${tokenOverride || this.token}`,
    };

    const t0 = performance.now();
    let res;
    try {
      res = await fetch(url.toString(), {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (networkErr) {
      this.onNetworkEvent?.({ type: "network_unreachable", error: networkErr });
      throw {
        status: 0,
        code: "backend_unreachable",
        message: `Cannot reach Noir Atelier API at ${this.baseUrl}. Ensure FastAPI backend is running.`,
        trace_id: "TRC-NETERR",
      };
    }

    const latencyMs = Math.round(performance.now() - t0);
    if (latencyMs >= this.slowThresholdMs) {
      this.onNetworkEvent?.({ type: "slow_network", latencyMs });
    }

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (res.status === 401) {
        this.onNetworkEvent?.({ type: "session_expired", status: 401, data });
      } else if (res.status === 403) {
        this.onNetworkEvent?.({
          type: "permission_denied",
          status: 403,
          data,
          endpoint: `${method} ${path}`,
        });
      }
      throw {
        status: res.status,
        code: data.code || "http_error",
        message: data.message || `HTTP ${res.status}`,
        trace_id: data.trace_id || "TRC-000000",
      };
    }

    return { data, latencyMs };
  }

  async getHealth() {
    const { data } = await this.request("GET", "/health");
    return data;
  }

  async getPoliciesAndConfig() {
    const { data } = await this.request("GET", "/api/config/policies");
    return data;
  }

  async listCategories() {
    const { data } = await this.request("GET", "/api/categories");
    return data;
  }

  async searchProducts({ q = "", category = "", department = "", maxPrice = null, inStockOnly = false } = {}) {
    const { data } = await this.request("GET", "/api/products/search", {
      params: {
        q: q || undefined,
        category: category || undefined,
        department: department && department !== "ALL" ? department : undefined,
        max_price: maxPrice || undefined,
        in_stock_only: inStockOnly || undefined,
      },
    });
    return data;
  }

  async getProductDetails(productId) {
    const { data } = await this.request("GET", `/api/products/${productId}`);
    return data;
  }

  async getRecommendations(productId) {
    const { data } = await this.request("GET", `/api/products/${productId}/recommendations`);
    return data;
  }

  async getCustomerProfile(customerId) {
    const { data } = await this.request("GET", `/api/customers/${customerId}`);
    return data;
  }

  async listCustomerAddresses(customerId) {
    const { data } = await this.request("GET", `/api/customers/${customerId}/addresses`);
    return data;
  }

  async getCart({ couponCode = null } = {}) {
    const { data } = await this.request("GET", "/api/cart", {
      params: { coupon_code: couponCode || undefined },
    });
    return data;
  }

  async addToCart({ productId, size = "M", quantity = 1 }) {
    const { data } = await this.request("POST", "/api/cart/add", {
      body: { product_id: productId, size, quantity },
    });
    return data;
  }

  async removeCartItem(cartId) {
    const { data } = await this.request("DELETE", `/api/cart/remove/${cartId}`);
    return data;
  }

  async clearCart() {
    const { data } = await this.request("POST", "/api/cart/clear");
    return data;
  }

  async validateCoupon(code, cartTotalInr) {
    const { data } = await this.request("POST", "/api/coupons/validate", {
      body: { code, cart_total_inr: cartTotalInr },
    });
    return data;
  }

  async calculateOrderPreview({ items, couponCode = null, destinationState = "Tamil Nadu", destinationPin = "600086" }) {
    const { data } = await this.request("POST", "/api/orders/calculate", {
      body: {
        items,
        coupon_code: couponCode || undefined,
        destination_state: destinationState,
        destination_pin: destinationPin,
      },
    });
    return data;
  }

  async createOrder({ customerId, items = null, couponCode = null, paymentMethod = "upi", requestKey = null }) {
    const { data } = await this.request("POST", "/api/orders", {
      body: {
        customer_id: customerId,
        items: items || undefined,
        coupon_code: couponCode || undefined,
        payment_method: paymentMethod,
        request_key: requestKey || undefined,
      },
    });
    return data;
  }

  async listOrders(customerId = null) {
    const { data } = await this.request("GET", "/api/orders", {
      params: { customer_id: customerId || undefined },
    });
    return data;
  }

  async cancelOrder(orderId, reason = "Customer requested pre-shipment cancellation") {
    const { data } = await this.request("POST", `/api/orders/${orderId}/cancel`, {
      body: { reason },
    });
    return data;
  }

  async scheduleShipment(orderId, carrier = "Noir Express", tokenOverride = null) {
    const { data } = await this.request("POST", "/api/shipments/schedule", {
      body: { order_id: orderId, carrier },
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async initiateReturn({
    orderId,
    reasonCategory = "size_mismatch",
    customerNotes = "",
    tagIntact = true,
    qcPassed = true,
    isDefectiveClaim = false,
  }) {
    const { data } = await this.request("POST", "/api/returns", {
      body: {
        order_id: orderId,
        reason_category: reasonCategory,
        customer_notes: customerNotes,
        tag_intact: tagIntact,
        qc_passed: qcPassed,
        is_defective_claim: isDefectiveClaim,
      },
    });
    return data;
  }

  async listRefunds(tokenOverride = null) {
    const { data } = await this.request("GET", "/api/refunds", {
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async approveRefund(refundId, reason, tokenOverride = null) {
    const { data } = await this.request("POST", `/api/refunds/${refundId}/approve`, {
      body: { reason },
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async processRefund(refundId, tokenOverride = null) {
    const { data } = await this.request("POST", `/api/refunds/${refundId}/process`, {
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async listInventory(lowStockOnly = false, tokenOverride = null) {
    const { data } = await this.request("GET", "/api/inventory/list", {
      params: { low_stock_only: lowStockOnly },
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async updateInventory(productId, quantityAvailable, reason = "admin_stock_adjustment", tokenOverride = null) {
    const { data } = await this.request("PUT", `/api/inventory/${productId}`, {
      body: { quantity_available: Number(quantityAvailable), reason },
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async getAdminDashboard(tokenOverride = null) {
    const { data } = await this.request("GET", "/api/admin/dashboard", {
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async updateBusinessConfig(configKey, configValue, reason, tokenOverride = null) {
    const { data } = await this.request("PUT", "/api/admin/config/policies", {
      body: { config_key: configKey, config_value: configValue, reason },
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async getAuditLog(limit = 25, tokenOverride = null) {
    const { data } = await this.request("GET", "/api/audit/log", {
      params: { limit },
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async getAgentsRegistry() {
    const { data } = await this.request("GET", "/api/agents/registry");
    return data;
  }

  async chatWithAgents({ message, customerId, actorRole, preferredAgent = null }) {
    const { data } = await this.request("POST", "/api/agents/chat", {
      body: {
        message,
        customer_id: customerId,
        actor_role: actorRole,
        preferred_agent: preferredAgent || undefined,
      },
    });
    return data;
  }
}
