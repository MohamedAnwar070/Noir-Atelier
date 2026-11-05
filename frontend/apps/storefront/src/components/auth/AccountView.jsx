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
    askStylist,
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
      title="Sign In to View Your Maison Profile"
      description="Access your Noir Atelier client dossier, bespoke wardrobe acquisitions, delivery addresses, and personal fashion consultant."
    >
      <div className="page-container">
        <div className="page-header">
          <div>
            <span className="hero-eyebrow">Private Client Dossier</span>
            <h1 className="page-heading">{profile?.name || "Client Profile"}</h1>
            <p className="page-subheading">
              {isStaff ? (
                <span>Atelier Personnel · Authorized Governance Profile</span>
              ) : (
                <span>Maison Private Client · Obsidian Privileged Member</span>
              )}
            </p>
          </div>
          <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn-pill btn-pill-outline btn-sm"
              onClick={() => askStylist()}
            >
              <Icon name="sparkles" size={14} />
              <span>Consult Stylist</span>
            </button>
            {isStaff && (
              <button
                type="button"
                className="btn-pill btn-pill-outline btn-sm"
                onClick={() => navigateTo("admin")}
              >
                <Icon name="shield" size={14} />
                <span>Atelier Governance</span>
              </button>
            )}
            <button
              type="button"
              className="btn-pill btn-pill-outline btn-sm"
              onClick={() => navigateTo("orders")}
            >
              <Icon name="package" size={14} />
              <span>Orders &amp; Returns</span>
            </button>
            <button type="button" className="btn-pill btn-sm" onClick={logout}>
              <Icon name="logout" size={14} />
              <span>Sign Out</span>
            </button>
          </div>
        </div>

        <div className="account-grid">
          {/* Private Client Profile & Native AI Stylist */}
          <section className="account-card" aria-label="Private Client Profile">
            <div className="account-card-header">
              <h2 className="account-card-title">Maison Client Profile</h2>
              <span className="badge" data-tone="info">
                {isStaff ? (profile?.role_name || "Atelier Staff") : (profile?.loyalty_tier || "VIP Obsidian")}
              </span>
            </div>

            <dl className="account-kv-list">
              <div className="account-kv">
                <dt>Client Name</dt>
                <dd>{profile?.name || "Private Client"}</dd>
              </div>
              <div className="account-kv">
                <dt>Email Address</dt>
                <dd>{profile?.email || "—"}</dd>
              </div>
              <div className="account-kv">
                <dt>Membership Privileges</dt>
                <dd>Complimentary White-Glove Courier &amp; Security Ribbon Returns</dd>
              </div>
              <div className="account-kv">
                <dt>Personal Stylist (Native AI)</dt>
                <dd style={{ color: "var(--accent-gold)", fontWeight: 600 }}>Active &amp; Connected</dd>
              </div>
            </dl>

            <div style={{ marginTop: "var(--space-4)", paddingTop: "var(--space-4)", borderTop: "1px solid var(--border-subtle)" }}>
              <button
                type="button"
                className="btn-pill btn-pill-outline btn-sm"
                onClick={() => askStylist()}
                style={{ width: "100%", justifyContent: "center" }}
              >
                <Icon name="sparkles" size={14} />
                <span>Open Personal Fashion Stylist Consultation</span>
              </button>
            </div>
          </section>

          {/* Active Signed-In Devices */}
          <section className="account-card" aria-label="Active Security Sessions">
            <div className="account-card-header">
              <h2 className="account-card-title">Signed-In Devices</h2>
              <button
                type="button"
                className="btn-pill btn-pill-outline btn-sm"
                onClick={logoutAll}
              >
                <span>Sign Out All Devices</span>
              </button>
            </div>

            {loadingSessions ? (
              <p className="auth-subtitle">Checking active sessions…</p>
            ) : sessions.length === 0 ? (
              <p className="auth-subtitle">
                Current browser session is active.
              </p>
            ) : (
              <div className="session-list">
                {sessions.map((s) => (
                  <div key={s.session_id} className="session-row">
                    <div className="session-meta">
                      <strong>
                        {s.user_agent ? (s.user_agent.includes("Windows") ? "Desktop (Windows)" : s.user_agent.includes("Mac") ? "Desktop (macOS)" : s.user_agent.includes("iPhone") ? "Mobile (iPhone)" : "Web Browser") : "Atelier Web Browser"}{" "}
                        {s.is_current && (
                          <span className="badge" data-tone="success" style={{ marginLeft: 6 }}>
                            This Device
                          </span>
                        )}
                      </strong>
                      <span>IP Address: {s.ip_address || "Private Boutique Network"}</span>
                    </div>
                    {!s.is_current && (
                      <button
                        type="button"
                        className="btn-pill btn-pill-outline btn-sm"
                        onClick={() => handleRevokeSession(s.session_id)}
                      >
                        Sign Out Device
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
