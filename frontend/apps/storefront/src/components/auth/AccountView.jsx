"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useStore } from "@/store/StoreProvider";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { Icon } from "@/components/ui/Icon";

export function AccountView() {
  const {
    authUser,
    currentActor,
    isCustomer,
    isStaff,
    permissions,
    addresses,
    addCustomerAddress,
    apiClient,
    logout,
    logoutAll,
    notify,
    navigateTo,
  } = useStore();

  const [sessions, setSessions] = useState([]);
  const [loadingSessions, setLoadingSessions] = useState(false);

  // Password change state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [pwLoading, setPwLoading] = useState(false);
  const [pwError, setPwError] = useState("");

  // Address form state
  const [addrLabel, setAddrLabel] = useState("Residence");
  const [addrStreet, setAddrStreet] = useState("");
  const [addrCity, setAddrCity] = useState("");
  const [addrState, setAddrState] = useState("Tamil Nadu");
  const [addrPin, setAddrPin] = useState("");
  const [savingAddr, setSavingAddr] = useState(false);

  const fetchSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const list = await apiClient.listAuthSessions();
      setSessions(Array.isArray(list) ? list : []);
    } catch {
      setSessions([]);
    } finally {
      setLoadingSessions(false);
    }
  }, [apiClient]);

  useEffect(() => {
    if (currentActor?.actor_type && currentActor.actor_type !== "anon") {
      fetchSessions();
    }
  }, [currentActor?.actor_type, currentActor?.id, fetchSessions]);

  const handleRevokeSession = async (sessionId) => {
    try {
      await apiClient.revokeAuthSession(sessionId);
      notify({ tone: "info", title: "Session revoked", message: `Session ${sessionId} terminated.` });
      await fetchSessions();
    } catch (err) {
      notify({ tone: "error", title: "Could not revoke session", message: err?.message || "Failed." });
    }
  };

  const handlePasswordChange = async (e) => {
    e.preventDefault();
    setPwError("");
    setPwLoading(true);
    try {
      const res = await apiClient.changePassword({ currentPassword, newPassword });
      setCurrentPassword("");
      setNewPassword("");
      notify({
        tone: "success",
        title: "Password updated",
        message: `Argon2id credentials rotated. ${res.revoked_other_sessions || 0} other session(s) revoked.`,
      });
      await fetchSessions();
    } catch (err) {
      setPwError(err?.message || "Unable to update password.");
    } finally {
      setPwLoading(false);
    }
  };

  const handleSaveAddress = async (e) => {
    e.preventDefault();
    if (!addrStreet.trim() || !addrCity.trim() || !/^\d{6}$/.test(addrPin.trim())) {
      notify({ tone: "error", title: "Invalid address", message: "Enter street, city, and a valid 6-digit Indian PIN code." });
      return;
    }
    setSavingAddr(true);
    try {
      await addCustomerAddress({
        label: addrLabel,
        street: addrStreet.trim(),
        city: addrCity.trim(),
        state: addrState.trim(),
        pin_code: addrPin.trim(),
        is_primary: (addresses || []).length === 0,
      });
      setAddrStreet("");
      setAddrCity("");
      setAddrPin("");
      notify({ tone: "success", title: "Delivery address saved", message: "Added to your private client profile." });
    } catch (err) {
      notify({ tone: "error", title: "Could not save address", message: err?.message || "Error saving address." });
    } finally {
      setSavingAddr(false);
    }
  };

  const profile = authUser || currentActor;

  return (
    <ProtectedRoute
      requireAuth
      title="Sign In to View Your Maison Account"
      description="Manage your Noir Atelier profile, RBAC permissions, active security sessions, and delivery addresses."
    >
      <div className="page-container">
        <div className="page-header">
          <div>
            <span className="hero-eyebrow">Maison Identity &amp; Session Security</span>
            <h1 className="page-heading">{profile?.name || "Client Profile"}</h1>
            <p className="page-subheading">
              Authenticated as <strong>{profile?.role_name || profile?.role}</strong> · Account ID{" "}
              <code>{profile?.id}</code>
            </p>
          </div>
          <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
            {isStaff && (
              <button type="button" className="btn-pill btn-pill-outline btn-sm" onClick={() => navigateTo("admin")}>
                <Icon name="shield" size={14} />
                <span>Open Governance Console</span>
              </button>
            )}
            {isCustomer && (
              <button type="button" className="btn-pill btn-pill-outline btn-sm" onClick={() => navigateTo("orders")}>
                <Icon name="package" size={14} />
                <span>Your Orders</span>
              </button>
            )}
            <button type="button" className="btn-pill btn-sm" onClick={logout}>
              <Icon name="logout" size={14} />
              <span>Sign Out</span>
            </button>
          </div>
        </div>

        <div className="account-grid">
          {/* Identity & RBAC Permissions */}
          <section className="account-card" aria-label="Identity and RBAC permissions">
            <div className="account-card-header">
              <h2 className="account-card-title">Identity &amp; RBAC Privileges</h2>
              <span className="badge" data-tone="info">
                {profile?.role_name || profile?.role}
              </span>
            </div>

            <dl className="account-kv-list">
              <div className="account-kv">
                <dt>Email Address</dt>
                <dd>{profile?.email || "—"}</dd>
              </div>
              <div className="account-kv">
                <dt>Maison Identifier</dt>
                <dd style={{ fontFamily: "var(--font-mono)" }}>{profile?.id}</dd>
              </div>
              <div className="account-kv">
                <dt>Tier / Classification</dt>
                <dd>{profile?.loyalty_tier || "STANDARD"}</dd>
              </div>
              <div className="account-kv">
                <dt>Account Status</dt>
                <dd style={{ textTransform: "capitalize" }}>{profile?.status || "active"}</dd>
              </div>
            </dl>

            <div>
              <div className="auth-eyebrow" style={{ marginBottom: "var(--space-2)" }}>
                Granted Granular Permissions ({(permissions || []).length})
              </div>
              <div className="rbac-perm-cloud">
                {(permissions || []).map((perm) => (
                  <span key={perm} className="rbac-perm-chip">
                    {perm}
                  </span>
                ))}
              </div>
            </div>
          </section>

          {/* Active JWT Sessions */}
          <section className="account-card" aria-label="Active security sessions">
            <div className="account-card-header">
              <h2 className="account-card-title">Active JWT Sessions</h2>
              <button
                type="button"
                className="btn-pill btn-pill-outline btn-sm"
                onClick={logoutAll}
              >
                <span>Sign Out All Devices</span>
              </button>
            </div>

            {loadingSessions ? (
              <p className="auth-subtitle">Inspecting active refresh-token sessions…</p>
            ) : sessions.length === 0 ? (
              <p className="auth-subtitle">
                Browsing via stateless/demo token. Sign in with your email and password to manage
                rotating refresh-token sessions.
              </p>
            ) : (
              <div className="session-list">
                {sessions.map((s) => (
                  <div key={s.session_id} className="session-row">
                    <div className="session-meta">
                      <strong>
                        {s.session_id}{" "}
                        {s.is_current && (
                          <span className="badge" data-tone="success" style={{ marginLeft: 6 }}>
                            Current
                          </span>
                        )}
                      </strong>
                      <span>IP: {s.ip_address}</span>
                      <span>{(s.user_agent || "Web Browser").slice(0, 64)}</span>
                    </div>
                    {!s.is_current && (
                      <button
                        type="button"
                        className="btn-pill btn-pill-outline btn-sm"
                        onClick={() => handleRevokeSession(s.session_id)}
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Password Rotation */}
          <section className="account-card" aria-label="Change password">
            <div className="account-card-header">
              <h2 className="account-card-title">Rotate Password</h2>
              <Icon name="key" size={18} />
            </div>
            {pwError && (
              <div className="auth-error-banner" role="alert">
                <Icon name="alert" size={15} />
                <span>{pwError}</span>
              </div>
            )}
            <form className="auth-form" onSubmit={handlePasswordChange}>
              <div className="auth-field">
                <label htmlFor="acct-cur-pw">Current Password</label>
                <input
                  id="acct-cur-pw"
                  type="password"
                  required
                  autoComplete="current-password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                />
              </div>
              <div className="auth-field">
                <label htmlFor="acct-new-pw">New Strong Password</label>
                <input
                  id="acct-new-pw"
                  type="password"
                  required
                  autoComplete="new-password"
                  placeholder="Min 8 chars, upper, lower, digit & symbol"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
              <button type="submit" className="btn-pill btn-sm" disabled={pwLoading}>
                <span>{pwLoading ? "Updating…" : "Update Password & Revoke Other Sessions"}</span>
              </button>
            </form>
          </section>

          {/* Client Delivery Addresses */}
          {isCustomer && (
            <section className="account-card" aria-label="Saved delivery addresses">
              <div className="account-card-header">
                <h2 className="account-card-title">Courier Destinations</h2>
                <Icon name="truck" size={18} />
              </div>

              {(addresses || []).length > 0 && (
                <div className="session-list">
                  {addresses.map((a) => (
                    <div key={a.address_id} className="session-row">
                      <div className="session-meta">
                        <strong>
                          {a.label} {a.is_primary ? "· Primary" : ""}
                        </strong>
                        <span>
                          {a.street}, {a.city}, {a.state} — {a.pin_code}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <form className="auth-form" onSubmit={handleSaveAddress}>
                <div className="auth-form-row">
                  <div className="auth-field">
                    <label htmlFor="addr-lbl">Label</label>
                    <input
                      id="addr-lbl"
                      type="text"
                      value={addrLabel}
                      onChange={(e) => setAddrLabel(e.target.value)}
                    />
                  </div>
                  <div className="auth-field">
                    <label htmlFor="addr-pin">6-Digit PIN Code</label>
                    <input
                      id="addr-pin"
                      type="text"
                      maxLength={6}
                      placeholder="600086"
                      value={addrPin}
                      onChange={(e) => setAddrPin(e.target.value)}
                    />
                  </div>
                </div>
                <div className="auth-field">
                  <label htmlFor="addr-street">Street &amp; Residence</label>
                  <input
                    id="addr-street"
                    type="text"
                    placeholder="14 Cathedral Road"
                    value={addrStreet}
                    onChange={(e) => setAddrStreet(e.target.value)}
                  />
                </div>
                <div className="auth-form-row">
                  <div className="auth-field">
                    <label htmlFor="addr-city">City</label>
                    <input
                      id="addr-city"
                      type="text"
                      placeholder="Chennai"
                      value={addrCity}
                      onChange={(e) => setAddrCity(e.target.value)}
                    />
                  </div>
                  <div className="auth-field">
                    <label htmlFor="addr-state">State</label>
                    <input
                      id="addr-state"
                      type="text"
                      value={addrState}
                      onChange={(e) => setAddrState(e.target.value)}
                    />
                  </div>
                </div>
                <button type="submit" className="btn-pill btn-pill-outline btn-sm" disabled={savingAddr}>
                  <Icon name="plus" size={14} />
                  <span>{savingAddr ? "Saving…" : "Add Delivery Destination"}</span>
                </button>
              </form>
            </section>
          )}
        </div>
      </div>
    </ProtectedRoute>
  );
}

export default AccountView;
