/**
 * FastAPI/Pydantic errors arrive as `{ detail: string | [{ loc, msg }] }`.
 * Turn them into a readable message plus a { field: message } map, so a 422
 * never surfaces to users as a bare "HTTP 422".
 */
function parseValidationDetail(detail) {
  if (!detail) return null;
  if (typeof detail === "string") return { message: detail, fields: {} };
  if (!Array.isArray(detail)) return null;
  const fields = {};
  for (const issue of detail) {
    const field = (issue.loc || []).filter((part) => part !== "body" && part !== "query").join(".") || "request";
    fields[field] = issue.msg;
  }
  const message = Object.entries(fields)
    .map(([field, msg]) => `${field}: ${msg}`)
    .join("; ");
  return { message: `Invalid request — ${message}`, fields };
}

export class NoirApiClient {
  constructor({
    baseUrl = "",
    token = null,
    refreshToken = null,
    slowThresholdMs = 1200,
    onNetworkEvent = null,
    onAuthSessionUpdate = null,
  } = {}) {
    this.baseUrl =
      baseUrl ||
      (typeof window !== "undefined" && window.NOIR_API_BASE) ||
      (typeof process !== "undefined" && process.env && process.env.NEXT_PUBLIC_API_BASE_URL) ||
      (typeof window !== "undefined" && window.location?.origin ? window.location.origin : "http://127.0.0.1:8000");
    this.token = token || null;
    this.refreshToken = refreshToken || null;
    this.slowThresholdMs = slowThresholdMs;
    this.onNetworkEvent = onNetworkEvent;
    this.onAuthSessionUpdate = onAuthSessionUpdate;
    this._refreshPromise = null;
  }

  setToken(token) {
    this.token = token || null;
  }

  setAuthTokens({ accessToken = null, refreshToken = null } = {}) {
    this.token = accessToken || null;
    if (refreshToken !== undefined) {
      this.refreshToken = refreshToken || null;
    }
  }

  clearAuthTokens() {
    this.token = null;
    this.refreshToken = null;
  }

  async _attemptTokenRefresh() {
    if (this._refreshPromise) {
      return this._refreshPromise;
    }
    this._refreshPromise = (async () => {
      try {
        const { data } = await this.request("POST", "/api/auth/refresh", {
          body: { refresh_token: this.refreshToken || undefined },
          skipAuthRefresh: true,
          omitAuthHeader: true,
        });
        if (data?.tokens?.access_token) {
          this.setAuthTokens({
            accessToken: data.tokens.access_token,
            refreshToken: data.tokens.refresh_token || this.refreshToken,
          });
          this.onAuthSessionUpdate?.(data);
          return data;
        }
        return null;
      } catch {
        this.clearAuthTokens();
        this.onAuthSessionUpdate?.(null);
        return null;
      } finally {
        this._refreshPromise = null;
      }
    })();
    return this._refreshPromise;
  }

  async request(
    method,
    path,
    { params = null, body = null, tokenOverride = null, skipAuthRefresh = false, omitAuthHeader = false } = {}
  ) {
    if (typeof navigator !== "undefined" && navigator.onLine === false) {
      this.onNetworkEvent?.({ type: "offline" });
      throw {
        status: 0,
        code: "offline",
        message: "You appear to be offline.",
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

    const effectiveToken = omitAuthHeader ? null : tokenOverride || this.token;
    const headers = {
      "Content-Type": "application/json",
    };
    if (effectiveToken) {
      headers.Authorization = `Bearer ${effectiveToken}`;
    }

    const t0 = performance.now();
    const slowTimer = setTimeout(() => {
      this.onNetworkEvent?.({ type: "slow_network", pending: true });
    }, this.slowThresholdMs);

    let res;
    try {
      res = await fetch(url.toString(), {
        method,
        headers,
        credentials: "include",
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch (networkErr) {
      clearTimeout(slowTimer);
      this.onNetworkEvent?.({ type: "network_unreachable", error: networkErr });
      throw {
        status: 0,
        code: "backend_unreachable",
        message: "We couldn't reach our servers. Please check your connection and try again.",
        trace_id: "TRC-NETERR",
      };
    }
    clearTimeout(slowTimer);

    const latencyMs = Math.round(performance.now() - t0);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const canTryRefresh =
        res.status === 401 &&
        !skipAuthRefresh &&
        !path.startsWith("/api/auth/") &&
        !tokenOverride &&
        Boolean(this.refreshToken || this.token);

      if (canTryRefresh) {
        const refreshed = await this._attemptTokenRefresh();
        if (refreshed?.tokens?.access_token) {
          return this.request(method, path, {
            params,
            body,
            skipAuthRefresh: true,
          });
        }
      }

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
      const validation = parseValidationDetail(data.detail);
      throw {
        status: res.status,
        code: data.code || data.error?.code || (validation ? "validation_error" : "http_error"),
        message: data.message || data.error?.message || validation?.message || `HTTP ${res.status}`,
        details: data.details || data.error?.details || (validation ? { fields: validation.fields } : {}),
        trace_id: data.trace_id || "TRC-000000",
      };
    }

    this.onNetworkEvent?.({ type: "request_ok", latencyMs, slow: latencyMs >= this.slowThresholdMs });
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

  async getCatalogMeta() {
    const { data } = await this.request("GET", "/api/catalog/meta");
    return data;
  }

  async listCategories() {
    const { data } = await this.request("GET", "/api/categories");
    return data;
  }

  _buildCatalogQueryParams({
    q = "",
    category = "",
    department = "",
    color = "",
    material = "",
    minPrice = null,
    maxPrice = null,
    inStockOnly = false,
    sort = "",
    limit = null,
    offset = null,
  } = {}) {
    return {
      q: q || undefined,
      category: category && category !== "all" ? category : undefined,
      department: department && department !== "ALL" ? department : undefined,
      color: color && color !== "all" ? color : undefined,
      material: material && material !== "all" ? material : undefined,
      min_price: minPrice != null && minPrice !== "" ? minPrice : undefined,
      max_price: maxPrice != null && maxPrice !== "" ? maxPrice : undefined,
      in_stock_only: inStockOnly ? true : undefined,
      sort: sort || undefined,
      limit: limit != null ? limit : undefined,
      offset: offset != null ? offset : undefined,
    };
  }

  /**
   * Database-driven catalogue search returning items, total count, and
   * natural-language query interpretation metadata.
   */
  async searchCatalog(filters = {}) {
    const { data } = await this.request("GET", "/api/catalog/search", {
      params: this._buildCatalogQueryParams(filters),
    });
    return data;
  }

  async searchProducts(filters = {}) {
    const { data } = await this.request("GET", "/api/products/search", {
      params: this._buildCatalogQueryParams(filters),
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

  async addProductReview(productId, { rating = 5, fitFeedback = "true_to_size", comment = "" }) {
    const { data } = await this.request("POST", `/api/products/${productId}/reviews`, {
      body: { rating: Number(rating), fit_feedback: fitFeedback, comment },
    });
    return data;
  }

  async createProduct(payload, tokenOverride = null) {
    const { data } = await this.request("POST", "/api/products", {
      body: payload,
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async listPaymentMethods() {
    const { data } = await this.request("GET", "/api/config/payment-methods");
    return data;
  }

  async getInvoice(identifier) {
    const { data } = await this.request("GET", `/api/invoices/${identifier}`);
    return data;
  }

  async getShipment(identifier) {
    const { data } = await this.request("GET", `/api/shipments/${identifier}`);
    return data;
  }

  async listSupportTickets(tokenOverride = null) {
    const { data } = await this.request("GET", "/api/support/tickets", {
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async resolveSupportTicket(ticketId, tokenOverride = null) {
    const { data } = await this.request("POST", `/api/support/tickets/${ticketId}/resolve`, {
      tokenOverride: tokenOverride || this.token,
    });
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

  async createOrder({ customerId, items = null, couponCode = null, paymentMethod = "upi", requestKey = null, shippingAddressId = null }) {
    const { data } = await this.request("POST", "/api/orders", {
      body: {
        customer_id: customerId,
        items: items || undefined,
        coupon_code: couponCode || undefined,
        payment_method: paymentMethod,
        shipping_address_id: shippingAddressId || undefined,
        request_key: requestKey || undefined,
      },
    });
    return data;
  }

  async holdOrder({ customerId, items = null, couponCode = null, paymentMethod = "upi", requestKey = null, shippingAddressId = null }) {
    const { data } = await this.request("POST", "/api/orders/hold", {
      body: {
        customer_id: customerId,
        items: items || undefined,
        coupon_code: couponCode || undefined,
        payment_method: paymentMethod,
        shipping_address_id: shippingAddressId || undefined,
        request_key: requestKey || undefined,
      },
    });
    return data;
  }

  async payForOrder(orderId) {
    const { data } = await this.request("POST", `/api/payments/demo/${orderId}`);
    return data;
  }

  async getOrder(orderId) {
    const { data } = await this.request("GET", `/api/orders/${orderId}`);
    return data;
  }

  async addCustomerAddress(customerId, address) {
    const { data } = await this.request("POST", `/api/customers/${customerId}/addresses`, {
      body: address,
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

  /** Adds `quantity` units to available stock (relative; use updateInventory to set an absolute level). */
  async restockInventory(productId, quantity, tokenOverride = null) {
    const { data } = await this.request("POST", "/api/inventory/restock", {
      body: { product_id: productId, quantity: Number(quantity) },
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

  async listCatalogSynonyms({ dimension = null } = {}, tokenOverride = null) {
    const { data } = await this.request("GET", "/api/admin/catalog/synonyms", {
      params: { dimension: dimension || undefined },
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async createCatalogSynonym({ term, dimension, value, target }, tokenOverride = null) {
    const { data } = await this.request("POST", "/api/admin/catalog/synonyms", {
      body: { term, dimension, value: value ?? target },
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async deleteCatalogSynonym(synonymId, tokenOverride = null) {
    const { data } = await this.request("DELETE", `/api/admin/catalog/synonyms/${synonymId}`, {
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async createCatalogColor({ colorId = null, name, family, hexCode, displayOrder = 0 }, tokenOverride = null) {
    const { data } = await this.request("POST", "/api/admin/catalog/colors", {
      body: {
        color_id: colorId || undefined,
        name,
        family,
        hex_code: hexCode,
        display_order: Number(displayOrder),
      },
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async createCatalogMaterial(
    { materialId = null, name, family, hsnDefault = "62", isNaturalFiber = true },
    tokenOverride = null
  ) {
    const { data } = await this.request("POST", "/api/admin/catalog/materials", {
      body: {
        material_id: materialId || undefined,
        name,
        family,
        hsn_default: hsnDefault,
        is_natural_fiber: Boolean(isNaturalFiber),
      },
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async createCatalogCategory(
    { categoryId = null, slug, name, parentId = null, description = "", displayOrder = 0 },
    tokenOverride = null
  ) {
    const { data } = await this.request("POST", "/api/admin/catalog/categories", {
      body: {
        category_id: categoryId || undefined,
        slug,
        name,
        parent_id: parentId || null,
        description,
        display_order: Number(displayOrder),
      },
      tokenOverride: tokenOverride || this.token,
    });
    return data;
  }

  async createCatalogDepartment({ code, name, description = "", displayOrder = 0 }, tokenOverride = null) {
    const { data } = await this.request("POST", "/api/admin/catalog/departments", {
      body: {
        code,
        name,
        description,
        display_order: Number(displayOrder),
      },
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

  async chatWithAgents({ message, customerId, actorRole, sessionId = null, preferredAgent = null }) {
    const { data } = await this.request("POST", "/api/agents/chat", {
      body: {
        message,
        customer_id: customerId,
        actor_role: actorRole,
        session_id: sessionId || undefined,
        preferred_agent: preferredAgent || undefined,
      },
    });
    return data;
  }

  /* ── Authentication, Sessions & RBAC Governance ────────────────────── */

  async listRoles() {
    const { data } = await this.request("GET", "/api/auth/roles", { skipAuthRefresh: true });
    return data;
  }

  async registerCustomer({ name, email, password, phone = null, preferredDepartment = null }) {
    const { data } = await this.request("POST", "/api/auth/register", {
      body: {
        name,
        email,
        password,
        phone: phone || undefined,
        preferred_department: preferredDepartment || undefined,
      },
      skipAuthRefresh: true,
      omitAuthHeader: true,
    });
    if (data?.tokens?.access_token) {
      this.setAuthTokens({
        accessToken: data.tokens.access_token,
        refreshToken: data.tokens.refresh_token,
      });
    }
    return data;
  }

  async registerAdmin({
    name,
    email,
    password,
    roleCode = "manager",
    phone = null,
    departmentScope = null,
    inviteCode = null,
  }) {
    const { data } = await this.request("POST", "/api/auth/register/admin", {
      body: {
        name,
        email,
        password,
        role_code: roleCode,
        phone: phone || undefined,
        department_scope: departmentScope || undefined,
        invite_code: inviteCode || undefined,
      },
      skipAuthRefresh: true,
    });
    if (data?.tokens?.access_token) {
      this.setAuthTokens({
        accessToken: data.tokens.access_token,
        refreshToken: data.tokens.refresh_token,
      });
    }
    return data;
  }

  async login({ email, password, portal = "auto" }) {
    const { data } = await this.request("POST", "/api/auth/login", {
      body: { email, password, portal },
      skipAuthRefresh: true,
      omitAuthHeader: true,
    });
    if (data?.tokens?.access_token) {
      this.setAuthTokens({
        accessToken: data.tokens.access_token,
        refreshToken: data.tokens.refresh_token,
      });
    }
    return data;
  }

  async refreshAuthSession(refreshToken = null) {
    const { data } = await this.request("POST", "/api/auth/refresh", {
      body: { refresh_token: refreshToken || this.refreshToken || undefined },
      skipAuthRefresh: true,
      omitAuthHeader: true,
    });
    if (data?.tokens?.access_token) {
      this.setAuthTokens({
        accessToken: data.tokens.access_token,
        refreshToken: data.tokens.refresh_token,
      });
    }
    return data;
  }

  async logout(refreshToken = null) {
    try {
      const { data } = await this.request("POST", "/api/auth/logout", {
        body: { refresh_token: refreshToken || this.refreshToken || undefined },
        skipAuthRefresh: true,
      });
      return data;
    } finally {
      this.clearAuthTokens();
    }
  }

  async logoutAllSessions() {
    try {
      const { data } = await this.request("POST", "/api/auth/logout-all", {
        skipAuthRefresh: true,
      });
      return data;
    } finally {
      this.clearAuthTokens();
    }
  }

  async getCurrentUser() {
    const { data } = await this.request("GET", "/api/auth/me");
    return data;
  }

  async listAuthSessions() {
    const { data } = await this.request("GET", "/api/auth/sessions");
    return data;
  }

  async revokeAuthSession(sessionId) {
    const { data } = await this.request("DELETE", `/api/auth/sessions/${sessionId}`);
    return data;
  }

  async changePassword({ currentPassword, newPassword }) {
    const { data } = await this.request("POST", "/api/auth/change-password", {
      body: { current_password: currentPassword, new_password: newPassword },
    });
    return data;
  }

  async getRbacMatrix() {
    const { data } = await this.request("GET", "/api/admin/rbac/matrix");
    return data;
  }

  async listAdminUsers() {
    const { data } = await this.request("GET", "/api/admin/users");
    return data;
  }

  async createStaffUser({ name, email, password, roleCode, phone = null, departmentScope = null }) {
    const { data } = await this.request("POST", "/api/admin/users/staff", {
      body: {
        name,
        email,
        password,
        role_code: roleCode,
        phone: phone || undefined,
        department_scope: departmentScope || undefined,
      },
    });
    return data;
  }

  async updateStaffUser(staffId, { roleCode = null, status = null, departmentScope = null, name = null }) {
    const { data } = await this.request("PATCH", `/api/admin/users/staff/${staffId}`, {
      body: {
        role_code: roleCode ?? undefined,
        status: status ?? undefined,
        department_scope: departmentScope ?? undefined,
        name: name ?? undefined,
      },
    });
    return data;
  }

  async updateCustomerStatus(customerId, { status = null, loyaltyTier = null }) {
    const { data } = await this.request("PATCH", `/api/admin/users/customers/${customerId}/status`, {
      body: {
        status: status ?? undefined,
        loyalty_tier: loyaltyTier ?? undefined,
      },
    });
    return data;
  }
}
