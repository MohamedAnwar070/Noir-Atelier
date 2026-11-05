"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useStore } from "@/store/StoreProvider";
import { StatePanel, ListSkeleton } from "@/components/ui/StatePanel";
import { Badge, Button, TextField } from "@/components/ui/Controls";
import { formatInr, formatPriceRange } from "@noir/utils/formatters.js";

/** Units added by the vault's quick-restock button (per size). */
const RESTOCK_UNITS = 5;

export function AdminView() {
  const {
    currentActor,
    isStaff,
    switchActor,
    actorsList,
    apiClient,
    notify,
    catalog,
    allProducts,
    catalogMeta,
    refreshCatalogMeta,
    refreshCatalog,
  } = useStore();

  const [activeTab, setActiveTab] = useState("kpis");
  const [inventoryQuery, setInventoryQuery] = useState("");
  // Per-size stock rows from /api/inventory/list (thresholds and reservations are per size).
  const [inventoryRows, setInventoryRows] = useState([]);
  const [restockSize, setRestockSize] = useState({});
  const [dashboardData, setDashboardData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState(null);

  // Returns queue state
  const [returnsQueue, setReturnsQueue] = useState([]);
  const [approvingRma, setApprovingRma] = useState(null);

  // Search vocabulary & attributes state
  const [synonyms, setSynonyms] = useState([]);
  const [synForm, setSynForm] = useState({ term: "", dimension: "product_type", value: "" });
  const [colorForm, setColorForm] = useState({ name: "", family: "", hexCode: "#181817" });
  const [materialForm, setMaterialForm] = useState({ name: "", family: "", hsnDefault: "62" });
  const [isSavingVocab, setIsSavingVocab] = useState(false);

  // Staff & RBAC governance state
  const [staffUsers, setStaffUsers] = useState([]);
  const [rbacMatrix, setRbacMatrix] = useState({ roles: [] });
  const [staffForm, setStaffForm] = useState({
    name: "",
    email: "",
    password: "",
    roleCode: "manager",
    phone: "",
    departmentScope: "",
  });
  const [isCreatingStaff, setIsCreatingStaff] = useState(false);

  // Staff-assignable roles come from the RBAC matrix (highest hierarchy first).
  const staffRoles = useMemo(
    () => (rbacMatrix.roles || []).filter((r) => r.actor_type === "admin"),
    [rbacMatrix.roles]
  );
  const permissionCount = useMemo(
    () => new Set((rbacMatrix.roles || []).flatMap((r) => r.permissions || [])).size,
    [rbacMatrix.roles]
  );

  useEffect(() => {
    if (staffRoles.length > 0 && !staffRoles.some((r) => r.role_code === staffForm.roleCode)) {
      setStaffForm((prev) => ({ ...prev, roleCode: staffRoles[staffRoles.length - 1].role_code }));
    }
  }, [staffRoles, staffForm.roleCode]);

  const productsById = useMemo(
    () => new Map((allProducts?.length ? allProducts : catalog || []).map((p) => [p.product_id, p])),
    [allProducts, catalog]
  );

  const refundStatusMap = useMemo(() => {
    const map = {};
    for (const row of catalogMeta?.refund_statuses || []) {
      map[row.code] = row;
    }
    return map;
  }, [catalogMeta?.refund_statuses]);

  // Dimensions and their valid canonical targets come from the server (catalog meta).
  const synonymDimensions = catalogMeta?.synonym_dimensions || [];
  const targetOptionsForDimension = useMemo(
    () =>
      (synonymDimensions.find((d) => d.code === synForm.dimension)?.options || []).map((o) => ({
        value: o.value,
        label: `${o.label} (${o.value})`,
      })),
    [synonymDimensions, synForm.dimension]
  );

  useEffect(() => {
    if (targetOptionsForDimension.length > 0 && !targetOptionsForDimension.some((o) => o.value === synForm.value)) {
      setSynForm((prev) => ({ ...prev, value: targetOptionsForDimension[0].value }));
    }
  }, [targetOptionsForDimension, synForm.value]);

  const isRefundPending = (refund) =>
    Boolean(refund?.awaiting_approval ?? refundStatusMap[refund?.status]?.awaiting_approval);

  const loadAdminData = async () => {
    setIsLoading(true);
    setAuthError(null);
    try {
      const [data, refunds, synRows, usersData, matrixData, invRows] = await Promise.all([
        apiClient.getAdminDashboard(),
        apiClient.listRefunds().catch(() => []),
        apiClient.listCatalogSynonyms().catch(() => []),
        apiClient.listAdminUsers().catch(() => ({ staff: [], customers: [] })),
        apiClient.getRbacMatrix().catch(() => ({ roles: [] })),
        apiClient.listInventory().catch(() => []),
      ]);
      setDashboardData(data);
      setReturnsQueue((Array.isArray(refunds) ? refunds : []).filter(isRefundPending));
      setSynonyms(Array.isArray(synRows) ? synRows : []);
      setStaffUsers(Array.isArray(usersData?.staff) ? usersData.staff : []);
      setRbacMatrix(matrixData || { roles: [] });
      setInventoryRows(Array.isArray(invRows) ? invRows : []);
    } catch (err) {
      if (err.status === 403 || err.code === "permission_denied") {
        setAuthError(
          `Actor ${currentActor.token} (${currentActor.role}) is not authorized to access governance telemetry.`
        );
      } else {
        setAuthError(err.message || "Failed to load admin analytics.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isStaff) {
      loadAdminData();
    } else {
      setIsLoading(false);
    }
  }, [currentActor, isStaff]);

  const handleSwitchToManager = () => {
    const mgr = (actorsList || []).find((a) => a.is_staff || a.actor_type === "admin" || a.role === "manager");
    if (mgr) {
      switchActor(mgr.token);
    }
  };

  const handleApproveReturn = async (refundId) => {
    setApprovingRma(refundId);
    try {
      const updated = await apiClient.approveRefund(refundId, "policy_verified_qc_passed");
      const stillPending = isRefundPending(updated);
      notify({
        type: "success",
        title: stillPending ? "First approval recorded" : "Refund approved",
        description: stillPending
          ? `Refund #${refundId} is Tier 3 and now needs a second admin (Finance) approval.`
          : `Refund #${refundId} approved for payout to the original payment method.`,
      });
      setReturnsQueue((prev) =>
        stillPending
          ? prev.map((r) => (r.refund_id === refundId ? { ...r, ...updated } : r))
          : prev.filter((r) => r.refund_id !== refundId)
      );
    } catch (err) {
      notify({
        type: "error",
        title: "Approval Failed",
        description: err.message || "Could not approve refund.",
      });
    } finally {
      setApprovingRma(null);
    }
  };

  const handleRestockProduct = async (row) => {
    const size = restockSize[row.product_id] || row.sizes?.[0]?.size;
    if (!size) return;
    try {
      const updated = await apiClient.restockInventory(row.product_id, size, RESTOCK_UNITS);
      setInventoryRows((rows) =>
        rows.map((r) => (r.product_id === row.product_id ? { ...r, ...updated, quantity_available: updated.stock } : r))
      );
      notify({
        type: "success",
        title: "Inventory Updated",
        description: `Added ${RESTOCK_UNITS} units of size ${size} for ${row.product_id}.`,
      });
      await refreshCatalog();
    } catch (err) {
      notify({
        type: "error",
        title: "Restock failed",
        description: err.message || "Could not update inventory.",
      });
    }
  };

  const handleCreateSynonym = async (e) => {
    e.preventDefault();
    const term = synForm.term.trim().toLowerCase();
    if (!term || !synForm.value) return;
    setIsSavingVocab(true);
    try {
      const created = await apiClient.createCatalogSynonym({
        term,
        dimension: synForm.dimension,
        value: synForm.value,
      });
      setSynonyms((prev) => [created, ...prev.filter((s) => s.synonym_id !== created.synonym_id)]);
      setSynForm((prev) => ({ ...prev, term: "" }));
      await Promise.all([refreshCatalogMeta(), refreshCatalog()]);
      notify({
        type: "success",
        title: "Search synonym saved",
        description: `"${created.term}" now maps to ${created.dimension}: ${created.value}.`,
      });
    } catch (err) {
      notify({
        type: "error",
        title: "Could not save synonym",
        description: err.message || "Check the synonym term and target.",
      });
    } finally {
      setIsSavingVocab(false);
    }
  };

  const handleDeleteSynonym = async (synonymId, term) => {
    try {
      await apiClient.deleteCatalogSynonym(synonymId);
      setSynonyms((prev) => prev.filter((s) => s.synonym_id !== synonymId));
      await refreshCatalog();
      notify({
        type: "info",
        title: "Synonym removed",
        description: `Removed search mapping for "${term}".`,
      });
    } catch (err) {
      notify({
        type: "error",
        title: "Could not delete synonym",
        description: err.message || "Failed to delete synonym.",
      });
    }
  };

  const handleCreateColor = async (e) => {
    e.preventDefault();
    if (!colorForm.name.trim() || !colorForm.family.trim()) return;
    setIsSavingVocab(true);
    try {
      const created = await apiClient.createCatalogColor(colorForm);
      setColorForm({ name: "", family: "", hexCode: "#181817" });
      await refreshCatalogMeta();
      notify({
        type: "success",
        title: "Palette colour added",
        description: `${created.name} (${created.family}) added to catalogue vocabulary.`,
      });
    } catch (err) {
      notify({
        type: "error",
        title: "Could not add colour",
        description: err.message || "Check colour name and hex code.",
      });
    } finally {
      setIsSavingVocab(false);
    }
  };

  const handleCreateMaterial = async (e) => {
    e.preventDefault();
    if (!materialForm.name.trim() || !materialForm.family.trim()) return;
    setIsSavingVocab(true);
    try {
      const created = await apiClient.createCatalogMaterial(materialForm);
      setMaterialForm({ name: "", family: "", hsnDefault: "62" });
      await refreshCatalogMeta();
      notify({
        type: "success",
        title: "Garment fiber added",
        description: `${created.name} (${created.family}) added to catalogue vocabulary.`,
      });
    } catch (err) {
      notify({
        type: "error",
        title: "Could not add fiber",
        description: err.message || "Check material details.",
      });
    } finally {
      setIsSavingVocab(false);
    }
  };

  const handleToggleStaffStatus = async (staff) => {
    const nextStatus = staff.status === "active" ? "suspended" : "active";
    try {
      await apiClient.updateStaffUser(staff.staff_id, { status: nextStatus });
      setStaffUsers((prev) =>
        prev.map((s) => (s.staff_id === staff.staff_id ? { ...s, status: nextStatus } : s))
      );
      notify({
        type: "success",
        title: "Staff Account Updated",
        description: `${staff.name} is now ${nextStatus}.`,
      });
    } catch (err) {
      notify({
        type: "error",
        title: "Failed to update staff status",
        description: err.message || "An error occurred.",
      });
    }
  };

  const handleCreateStaff = async (e) => {
    e.preventDefault();
    if (!staffForm.name || !staffForm.email || !staffForm.password) return;
    setIsCreatingStaff(true);
    try {
      const created = await apiClient.createStaffUser({
        name: staffForm.name.trim(),
        email: staffForm.email.trim(),
        password: staffForm.password,
        roleCode: staffForm.roleCode,
        phone: staffForm.phone?.trim() || null,
        departmentScope: staffForm.departmentScope?.trim() || null,
      });
      const newStaffObj = created.user || created;
      setStaffUsers((prev) => [newStaffObj, ...prev]);
      setStaffForm({
        name: "",
        email: "",
        password: "",
        roleCode: "manager",
        phone: "",
        departmentScope: "",
      });
      notify({
        type: "success",
        title: "Staff Member Provisioned",
        description: `${newStaffObj.name || staffForm.name} assigned role ${newStaffObj.role_name || staffForm.roleCode}.`,
      });
    } catch (err) {
      notify({
        type: "error",
        title: "Provisioning Failed",
        description: err.message || "Could not provision staff user.",
      });
    } finally {
      setIsCreatingStaff(false);
    }
  };

  // Principle 7: Permission Denied State
  if (!isStaff) {
    return (
      <div className="admin-permission-gate">
        <StatePanel
          type="permission_denied"
          title="Administrative Privilege Required (HTTP 403)"
          description={`Actor ${currentActor.label || currentActor.token} (${currentActor.role || "customer"}) is not authorized to access the governance portal. Required privilege: Store Manager or Finance Admin.`}
          actionLabel="Switch to Store Manager Token"
          onAction={handleSwitchToManager}
        />
      </div>
    );
  }

  const totalRevenue = Number(dashboardData?.orders?.total_revenue_inr ?? 0);
  const totalOrders = Number(dashboardData?.orders?.total_orders ?? 0);
  const computedAov = totalOrders > 0 ? totalRevenue / totalOrders : 0;
  const totalCustomers = Number(dashboardData?.customers?.total_customers ?? 0);
  const retentionPct = Number(dashboardData?.customers?.retention_rate_pct ?? 0);

  return (
    <div className="page-container admin-page-container">
      {/* Header */}
      <div className="page-header">
        <div>
          <span className="hero-eyebrow">Governance &amp; Executive Telemetry</span>
          <h1 className="page-heading">Atelier Admin Portal</h1>
          <p className="page-subheading">
            Live database telemetry, 4-tier refund authorization, inventory vault, and search vocabulary.
          </p>
        </div>

        <div className="admin-nav-tabs" role="tablist">
          <button
            type="button"
            className={`dept-tab-btn ${activeTab === "kpis" ? "active" : ""}`}
            onClick={() => setActiveTab("kpis")}
          >
            KPI Telemetry
          </button>
          <button
            type="button"
            className={`dept-tab-btn ${activeTab === "returns" ? "active" : ""}`}
            onClick={() => setActiveTab("returns")}
          >
            Return Approvals ({returnsQueue.length})
          </button>
          <button
            type="button"
            className={`dept-tab-btn ${activeTab === "inventory" ? "active" : ""}`}
            onClick={() => setActiveTab("inventory")}
          >
            Inventory Vault
          </button>
          <button
            type="button"
            className={`dept-tab-btn ${activeTab === "vocabulary" ? "active" : ""}`}
            onClick={() => setActiveTab("vocabulary")}
          >
            Search &amp; Vocabulary ({synonyms.length})
          </button>
          <button
            type="button"
            className={`dept-tab-btn ${activeTab === "rbac" ? "active" : ""}`}
            onClick={() => setActiveTab("rbac")}
          >
            RBAC &amp; Staff ({staffUsers.length})
          </button>
        </div>
      </div>

      {isLoading && <ListSkeleton count={4} />}

      {!isLoading && authError && (
        <StatePanel
          type="error"
          title="Telemetry Error"
          description={authError}
          actionLabel="Retry Telemetry"
          onAction={loadAdminData}
        />
      )}

      {/* KPI Cards (live database values from /api/admin/dashboard) */}
      {!isLoading && !authError && activeTab === "kpis" && (
        <div className="admin-kpis-section">
          <div className="kpi-cards-grid">
            <div className="kpi-card">
              <span className="kpi-label">Gross Merchandise Value</span>
              <span className="kpi-value">{formatInr(totalRevenue)}</span>
              <span className="kpi-trend positive">Live SQL aggregate</span>
            </div>

            <div className="kpi-card">
              <span className="kpi-label">Total Orders</span>
              <span className="kpi-value">{totalOrders}</span>
              <span className="kpi-trend positive">CBIC GST Invoiced</span>
            </div>

            <div className="kpi-card">
              <span className="kpi-label">Average Order Value</span>
              <span className="kpi-value">{formatInr(computedAov)}</span>
              <span className="kpi-trend">Dual HSN 61/62 Slabs</span>
            </div>

            <div className="kpi-card">
              <span className="kpi-label">Registered Clients</span>
              <span className="kpi-value">{totalCustomers}</span>
              <span className="kpi-trend positive">{retentionPct}% repeat retention</span>
            </div>
          </div>
        </div>
      )}

      {/* Returns Approval Queue (Database-Driven Refund Statuses) */}
      {!isLoading && !authError && activeTab === "returns" && (
        <div className="admin-returns-queue">
          <h3 className="section-subheading">4-Tier Luxury Return Approval Queue</h3>
          {returnsQueue.length === 0 ? (
            <StatePanel
              type="empty"
              title="All Returns Handled"
              description="No returns are currently awaiting studio tier review."
            />
          ) : (
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Refund</th>
                    <th>Return / Order</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Tier</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {returnsQueue.map((refund) => {
                    const statusLabel =
                      refund.status_label ||
                      refundStatusMap[refund.status]?.label ||
                      refund.status;
                    return (
                      <tr key={refund.refund_id}>
                        <td><strong>#{refund.refund_id}</strong></td>
                        <td>
                          {refund.return_id ? `#${refund.return_id} · ` : ""}#{refund.order_id}
                        </td>
                        <td>{formatInr(refund.amount_inr)}</td>
                        <td>
                          <span className="badge status-pill status-pending">
                            {statusLabel}
                          </span>
                        </td>
                        <td>Tier {refund.approval_tier}</td>
                        <td>
                          <div className="table-actions">
                            <button
                              type="button"
                              className="btn-pill btn-xs"
                              onClick={() => handleApproveReturn(refund.refund_id)}
                              disabled={approvingRma === refund.refund_id}
                            >
                              {approvingRma === refund.refund_id ? "Approving…" : "Approve refund"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Inventory Vault */}
      {!isLoading && !authError && activeTab === "inventory" && (
        <div className="admin-inventory-section">
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", marginBottom: "1rem" }}>
            <h3 className="section-subheading" style={{ margin: 0 }}>
              Atelier Archive Inventory ({inventoryRows.length} styles)
            </h3>
            <input
              type="search"
              className="input"
              style={{ maxWidth: "280px", minHeight: "36px", padding: "0.35rem 0.75rem", fontSize: "var(--text-xs)" }}
              placeholder="Filter SKU, name, or department…"
              value={inventoryQuery}
              onChange={(e) => setInventoryQuery(e.target.value)}
              aria-label="Filter inventory vault"
            />
          </div>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Product SKU</th>
                  <th>Garment Name</th>
                  <th>Department / Category</th>
                  <th>Stock by Size</th>
                  <th>Unit Price</th>
                  <th>Quick Restock</th>
                </tr>
              </thead>
              <tbody>
                {inventoryRows
                  .map((row) => ({ row, prod: productsById.get(row.product_id) }))
                  .filter(({ row, prod }) => {
                    const q = inventoryQuery.trim().toLowerCase();
                    if (!q) return true;
                    return [prod?.sku, row.product_id, row.name, prod?.department]
                      .some((v) => String(v || "").toLowerCase().includes(q));
                  })
                  .map(({ row, prod }) => (
                  <tr key={row.product_id}>
                    <td><code>{prod?.sku || row.product_id}</code></td>
                    <td>{row.name}</td>
                    <td>
                      {prod?.department}
                      {prod?.categoryName ? ` · ${prod.categoryName}` : ""}
                    </td>
                    <td>
                      <div className="stock-size-list">
                        {(row.sizes || []).map((sz) => (
                          <span
                            key={sz.size}
                            className={`badge stock-count-badge ${sz.low_stock_alert ? "low" : ""}`}
                            title={sz.quantity_reserved ? `${sz.quantity_reserved} held in checkout` : undefined}
                          >
                            {sz.size} · {sz.quantity_available}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>{prod ? formatPriceRange(prod) : "—"}</td>
                    <td>
                      <div className="stock-restock-control">
                        <select
                          className="select-control"
                          aria-label={`Size to restock for ${row.name}`}
                          value={restockSize[row.product_id] || row.sizes?.[0]?.size || ""}
                          onChange={(e) => setRestockSize((m) => ({ ...m, [row.product_id]: e.target.value }))}
                        >
                          {(row.sizes || []).map((sz) => (
                            <option key={sz.size} value={sz.size}>{sz.size}</option>
                          ))}
                        </select>
                        <button
                          type="button"
                          className="btn-pill btn-pill-outline btn-xs"
                          onClick={() => handleRestockProduct(row)}
                        >
                          + {RESTOCK_UNITS} Units
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Search Synonyms & Reference Vocabulary CRUD */}
      {!isLoading && !authError && activeTab === "vocabulary" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1.25rem" }}>
            {/* Add Search Synonym */}
            <form onSubmit={handleCreateSynonym} className="bag-summary-card form-stack">
              <h3 className="section-subheading" style={{ marginBottom: "0.25rem" }}>
                Add Search Synonym
              </h3>
              <p style={{ fontSize: "12px", color: "var(--text-secondary)", margin: 0 }}>
                Maps natural-language shopper terms (e.g. &ldquo;kurta&rdquo;, &ldquo;tee&rdquo;, &ldquo;noir&rdquo;) to structured database facets.
              </p>

              <TextField
                label="Search Term"
                value={synForm.term}
                onChange={(e) => setSynForm({ ...synForm, term: e.target.value })}
                placeholder="e.g. kurta"
                required
              />

              <div className="form-field-group">
                <label className="field-label" htmlFor="syn-dimension-select">Dimension</label>
                <select
                  id="syn-dimension-select"
                  className="select-control"
                  value={synForm.dimension}
                  onChange={(e) => setSynForm({ ...synForm, dimension: e.target.value, value: "" })}
                >
                  {synonymDimensions.map((d) => (
                    <option key={d.code} value={d.code}>{d.label}</option>
                  ))}
                </select>
              </div>

              <div className="form-field-group">
                <label className="field-label" htmlFor="syn-target-select">Target Canonical Value</label>
                <select
                  id="syn-target-select"
                  className="select-control"
                  value={synForm.value}
                  onChange={(e) => setSynForm({ ...synForm, value: e.target.value })}
                >
                  {targetOptionsForDimension.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>

              <Button type="submit" variant="primary" size="sm" isLoading={isSavingVocab}>
                Save Synonym Mapping
              </Button>
            </form>

            {/* Add Palette Colour & Garment Material */}
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              <form onSubmit={handleCreateColor} className="bag-summary-card form-stack">
                <h4 className="section-subheading" style={{ marginBottom: "0.15rem" }}>
                  Add Atelier Colour
                </h4>
                <div className="form-two-col">
                  <TextField
                    label="Shade Name"
                    value={colorForm.name}
                    onChange={(e) => setColorForm({ ...colorForm, name: e.target.value })}
                    placeholder="e.g. Forest Sage"
                    required
                  />
                  <TextField
                    label="Search Family"
                    value={colorForm.family}
                    onChange={(e) => setColorForm({ ...colorForm, family: e.target.value })}
                    placeholder="e.g. green"
                    required
                  />
                </div>
                <TextField
                  label="Hex Swatch"
                  value={colorForm.hexCode}
                  onChange={(e) => setColorForm({ ...colorForm, hexCode: e.target.value })}
                  placeholder="#3B4D3B"
                  required
                />
                <Button type="submit" variant="outline" size="sm" isLoading={isSavingVocab}>
                  Add Colour to Palette
                </Button>
              </form>

              <form onSubmit={handleCreateMaterial} className="bag-summary-card form-stack">
                <h4 className="section-subheading" style={{ marginBottom: "0.15rem" }}>
                  Add Garment Material
                </h4>
                <div className="form-two-col">
                  <TextField
                    label="Material Name"
                    value={materialForm.name}
                    onChange={(e) => setMaterialForm({ ...materialForm, name: e.target.value })}
                    placeholder="e.g. Himalayan Cashmere"
                    required
                  />
                  <TextField
                    label="Fiber Family"
                    value={materialForm.family}
                    onChange={(e) => setMaterialForm({ ...materialForm, family: e.target.value })}
                    placeholder="e.g. cashmere"
                    required
                  />
                </div>
                <Button type="submit" variant="outline" size="sm" isLoading={isSavingVocab}>
                  Add Material to Vocabulary
                </Button>
              </form>
            </div>
          </div>

          <div>
            <h3 className="section-subheading">Active Search Synonyms ({synonyms.length})</h3>
            <div className="admin-table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Shopper Term</th>
                    <th>Dimension</th>
                    <th>Canonical Value</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {synonyms.map((syn) => (
                    <tr key={syn.synonym_id}>
                      <td><strong>{syn.term}</strong></td>
                      <td><code>{syn.dimension}</code></td>
                      <td>{syn.value ?? syn.target}</td>
                      <td>{syn.is_active !== false ? "Active" : "Inactive"}</td>
                      <td>
                        <button
                          type="button"
                          className="btn-pill btn-pill-outline btn-xs"
                          onClick={() => handleDeleteSynonym(syn.synonym_id, syn.term)}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* RBAC Governance & Staff Directory */}
      {!isLoading && !authError && activeTab === "rbac" && (
        <div className="form-stack">
          {/* Staff Provisioning Form */}
          <div className="bag-summary-card" style={{ padding: "1.5rem" }}>
            <span className="hero-eyebrow">Maison Governance</span>
            <h3 className="section-subheading">
              Provision Atelier Staff Member
            </h3>
            <p className="section-subcaption">
              Issue administrative credentials with predefined Role-Based Access Control privileges.
            </p>
            <form onSubmit={handleCreateStaff} className="form-stack">
              <div className="form-two-col">
                <TextField
                  label="Full Name"
                  value={staffForm.name}
                  onChange={(e) => setStaffForm({ ...staffForm, name: e.target.value })}
                  placeholder="e.g. Elena Rostova"
                  required
                />
                <TextField
                  label="Maison Work Email"
                  type="email"
                  value={staffForm.email}
                  onChange={(e) => setStaffForm({ ...staffForm, email: e.target.value })}
                  placeholder="elena@noir.test"
                  required
                />
              </div>

              <div className="form-two-col">
                <TextField
                  label="Initial Password"
                  type="password"
                  value={staffForm.password}
                  onChange={(e) => setStaffForm({ ...staffForm, password: e.target.value })}
                  placeholder="Min 8 chars, mixed case, symbol"
                  required
                />
                <div className="form-field-group">
                  <label className="field-label" htmlFor="staff-role-select">Atelier RBAC Role</label>
                  <select
                    id="staff-role-select"
                    className="select-control"
                    value={staffForm.roleCode}
                    onChange={(e) => setStaffForm({ ...staffForm, roleCode: e.target.value })}
                    required
                  >
                    {staffRoles.map((r) => (
                      <option key={r.role_code} value={r.role_code}>
                        {r.name} ({r.role_code})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-two-col">
                <TextField
                  label="Phone (Optional)"
                  value={staffForm.phone}
                  onChange={(e) => setStaffForm({ ...staffForm, phone: e.target.value })}
                  placeholder="+91 98765 43210"
                />
                <TextField
                  label="Department Scope (Optional)"
                  value={staffForm.departmentScope}
                  onChange={(e) => setStaffForm({ ...staffForm, departmentScope: e.target.value })}
                  placeholder="e.g. MEN, WOMEN, HAUTE_COUTURE"
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "0.5rem" }}>
                <Button type="submit" variant="primary" size="md" isLoading={isCreatingStaff}>
                  Provision Staff Profile
                </Button>
              </div>
            </form>
          </div>

          {/* Active Staff Directory */}
          <div className="bag-summary-card" style={{ padding: "1.5rem" }}>
            <span className="hero-eyebrow">Staff Roster</span>
            <h3 className="section-subheading">
              Active Atelier Personnel ({staffUsers.length})
            </h3>

            <div className="rbac-user-table-wrap">
              <table className="rbac-user-table">
                <thead>
                  <tr>
                    <th>Staff Member</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Department Scope</th>
                    <th>Status</th>
                    <th>Last Active</th>
                    <th>Governance Action</th>
                  </tr>
                </thead>
                <tbody>
                  {staffUsers.map((staff) => (
                    <tr key={staff.staff_id}>
                      <td>
                        <strong>{staff.name}</strong>
                        <div style={{ fontSize: "11px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                          {staff.staff_id}
                        </div>
                      </td>
                      <td>{staff.email}</td>
                      <td>
                        <span className="rbac-perm-chip" style={{ fontWeight: 600 }}>
                          {staff.role_name || staff.role_code}
                        </span>
                      </td>
                      <td>{staff.department_scope || "Global Atelier"}</td>
                      <td>
                        <Badge tone={staff.status === "active" ? "success" : "error"}>
                          {staff.status === "active" ? "Active" : "Suspended"}
                        </Badge>
                      </td>
                      <td style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                        {staff.last_login_at ? new Date(staff.last_login_at).toLocaleDateString() : "Never"}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn-pill btn-pill-outline btn-xs"
                          onClick={() => handleToggleStaffStatus(staff)}
                        >
                          {staff.status === "active" ? "Suspend Access" : "Reactivate"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* RBAC Permission Matrix */}
          <div className="bag-summary-card" style={{ padding: "1.5rem" }}>
            <span className="hero-eyebrow">Security Architecture</span>
            <h3 className="section-subheading">
              Atelier Role &amp; Permission Matrix
            </h3>
            <p className="section-subcaption">
              Fine-grained access controls mapped across {(rbacMatrix.roles || []).length} roles and {permissionCount} atomic permissions.
            </p>

            <div className="rbac-role-cards">
              {(rbacMatrix.roles || []).map((r) => (
                <div key={r.role_code} className="rbac-role-card">
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <strong>{r.name}</strong>
                    <code style={{ fontSize: "11px", color: "var(--accent-gold)" }}>{r.role_code}</code>
                  </div>
                  <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: 0 }}>
                    {r.description}
                  </p>
                  <div>
                    <span style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-muted)" }}>
                      Granted Permissions ({r.permissions?.length || 0}):
                    </span>
                    <div className="rbac-perm-cloud" style={{ marginTop: "0.35rem" }}>
                      {(r.permissions || []).map((p) => (
                        <span key={p} className="rbac-perm-chip">
                          {p}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
