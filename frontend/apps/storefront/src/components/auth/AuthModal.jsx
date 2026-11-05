"use client";

import React, { useMemo, useState } from "react";
import { useStore } from "@/store/StoreProvider";
import { Modal } from "@/components/ui/Overlay";
import { BrandMonogram } from "@/components/ui/BrandLogo";
import { Icon } from "@/components/ui/Icon";

const DEMO_ACCOUNTS = [
  { label: "Arjun · VIP Client", email: "arjun@noir.test", pw: "NoirClient@2026", portal: "customer" },
  { label: "Executive Super Admin", email: "admin@noir.test", pw: "NoirAdmin@2026", portal: "admin" },
  { label: "Boutique Store Manager", email: "manager@noir.test", pw: "NoirAdmin@2026", portal: "admin" },
  { label: "Finance Controller", email: "finance@noir.test", pw: "NoirAdmin@2026", portal: "admin" },
  { label: "Archive Curator", email: "curator@noir.test", pw: "NoirAdmin@2026", portal: "admin" },
  { label: "Client Concierge", email: "concierge@noir.test", pw: "NoirAdmin@2026", portal: "admin" },
];

function evaluatePasswordRules(pw) {
  const val = pw || "";
  return [
    { id: "len", label: "8+ characters", met: val.length >= 8 },
    { id: "case", label: "Upper & lowercase", met: /[A-Z]/.test(val) && /[a-z]/.test(val) },
    { id: "num", label: "At least 1 number", met: /[0-9]/.test(val) },
    { id: "sym", label: "Special symbol (!@#)", met: /[^A-Za-z0-9]/.test(val) },
  ];
}

export function AuthFormPanel({ initialMode = "login", embedded = false, onSuccess = null }) {
  const {
    login,
    registerCustomer,
    registerAdmin,
    availableRoles,
    catalogMeta,
    config,
    navigateTo,
  } = useStore();

  const [mode, setMode] = useState(initialMode);
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  // Form fields
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [preferredDepartment, setPreferredDepartment] = useState("");
  const [portal, setPortal] = useState("auto");
  const [roleCode, setRoleCode] = useState("manager");
  const [inviteCode, setInviteCode] = useState("");

  const adminRoles = useMemo(
    () => (availableRoles || []).filter((r) => r.actor_type === "admin"),
    [availableRoles]
  );
  const departments = catalogMeta?.departments || [];
  const pwRules = useMemo(() => evaluatePasswordRules(password), [password]);
  const allPwRulesMet = pwRules.every((r) => r.met);

  const switchMode = (nextMode) => {
    setMode(nextMode);
    setErrorMsg("");
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMsg("");

    if (mode !== "login" && !allPwRulesMet) {
      setErrorMsg("Please satisfy all four password security requirements before continuing.");
      return;
    }

    setIsSubmitting(true);
    try {
      let res;
      if (mode === "login") {
        res = await login({ email: email.trim(), password, portal });
      } else if (mode === "register") {
        res = await registerCustomer({
          name: name.trim(),
          email: email.trim(),
          password,
          phone: phone.trim() || null,
          preferredDepartment: preferredDepartment || null,
        });
      } else {
        res = await registerAdmin({
          name: name.trim(),
          email: email.trim(),
          password,
          roleCode,
          phone: phone.trim() || null,
          inviteCode: inviteCode.trim() || null,
        });
      }
      if (onSuccess) {
        onSuccess(res);
      } else if (res?.user?.is_staff) {
        navigateTo("admin");
      } else {
        navigateTo("shop");
      }
    } catch (err) {
      setErrorMsg(err?.message || "Authentication could not be completed. Please verify your details.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleQuickDemoLogin = async (acct) => {
    setErrorMsg("");
    setEmail(acct.email);
    setPassword(acct.pw);
    setPortal(acct.portal);
    setMode("login");
    setIsSubmitting(true);
    try {
      const res = await login({ email: acct.email, password: acct.pw, portal: acct.portal });
      if (onSuccess) {
        onSuccess(res);
      } else if (res?.user?.is_staff) {
        navigateTo("admin");
      } else {
        navigateTo("shop");
      }
    } catch (err) {
      setErrorMsg(err?.message || "Quick sign-in failed.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className={`auth-panel ${embedded ? "auth-panel-embedded" : ""}`}>
      <div className="auth-brand-header">
        <BrandMonogram size={38} />
        <span className="auth-eyebrow">Maison de Haute Confection</span>
        <h2 className="auth-heading">
          {mode === "login"
            ? "Sign In to Noir Atelier"
            : mode === "register"
            ? "Create Client Membership"
            : "Maison Staff Provisioning"}
        </h2>
        <p className="auth-subtitle">
          {mode === "login"
            ? "Access your curated wardrobe bag, insured courier dispatches, or RBAC governance console."
            : mode === "register"
            ? "Register for private client privileges, saved delivery addresses, and 7-day security-seal returns."
            : "Provision an authorized Maison staff role using a verified Admin Provisioning Code."}
        </p>
      </div>

      <div className="auth-mode-tabs" role="tablist" aria-label="Authentication mode">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "login"}
          className={`auth-mode-tab ${mode === "login" ? "active" : ""}`}
          onClick={() => switchMode("login")}
        >
          Sign In
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "register"}
          className={`auth-mode-tab ${mode === "register" ? "active" : ""}`}
          onClick={() => switchMode("register")}
        >
          Client Signup
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "register_admin"}
          className={`auth-mode-tab ${mode === "register_admin" ? "active" : ""}`}
          onClick={() => switchMode("register_admin")}
        >
          Staff Signup
        </button>
      </div>

      {errorMsg && (
        <div className="auth-error-banner" role="alert" aria-live="assertive">
          <Icon name="alert" size={16} />
          <span>{errorMsg}</span>
        </div>
      )}

      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        {mode !== "login" && (
          <div className="auth-field">
            <label htmlFor="auth-name">Full Name</label>
            <input
              id="auth-name"
              type="text"
              required
              autoComplete="name"
              placeholder="e.g., Kavya Natarajan"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
        )}

        <div className="auth-field">
          <label htmlFor="auth-email">Email Address</label>
          <input
            id="auth-email"
            type="email"
            required
            autoComplete="email"
            placeholder="client@noiratelier.in"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        {mode === "register" && (
          <div className="auth-form-row">
            <div className="auth-field">
              <label htmlFor="auth-phone">Phone (Optional)</label>
              <input
                id="auth-phone"
                type="tel"
                autoComplete="tel"
                placeholder="+91-9840000000"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>
            <div className="auth-field">
              <label htmlFor="auth-dept">Preferred Collection</label>
              <select
                id="auth-dept"
                value={preferredDepartment}
                onChange={(e) => setPreferredDepartment(e.target.value)}
              >
                <option value="">All Collections</option>
                {departments.map((d) => (
                  <option key={d.code} value={d.code}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {mode === "register_admin" && (
          <div className="auth-form-row">
            <div className="auth-field">
              <label htmlFor="auth-staff-role">Assigned RBAC Role</label>
              <select
                id="auth-staff-role"
                value={roleCode}
                onChange={(e) => setRoleCode(e.target.value)}
              >
                {(adminRoles.length > 0
                  ? adminRoles
                  : [{ code: "manager", name: "Boutique Store Manager" }]
                ).map((r) => (
                  <option key={r.code} value={r.code}>
                    {r.name} ({r.code})
                  </option>
                ))}
              </select>
            </div>
            <div className="auth-field">
              <label htmlFor="auth-invite">Admin Provisioning Code</label>
              <input
                id="auth-invite"
                type="password"
                required
                placeholder="Enter Maison invite code"
                value={inviteCode}
                onChange={(e) => setInviteCode(e.target.value)}
              />
            </div>
          </div>
        )}

        {mode === "login" && (
          <div className="auth-field">
            <label htmlFor="auth-portal">Access Portal</label>
            <select
              id="auth-portal"
              value={portal}
              onChange={(e) => setPortal(e.target.value)}
            >
              <option value="auto">Automatic Detection (Client or Staff)</option>
              <option value="customer">Maison Client Portal</option>
              <option value="admin">Maison Staff &amp; Governance Portal</option>
            </select>
          </div>
        )}

        <div className="auth-field">
          <label htmlFor="auth-password">Password</label>
          <div className="auth-input-wrap">
            <input
              id="auth-password"
              type={showPassword ? "text" : "password"}
              required
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              placeholder={mode === "login" ? "Enter your password" : "Create a strong password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button
              type="button"
              className="auth-pw-toggle"
              onClick={() => setShowPassword((s) => !s)}
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              <Icon name={showPassword ? "eye-off" : "eye"} size={15} />
            </button>
          </div>

          {mode !== "login" && (
            <div className="auth-pw-rules" aria-live="polite">
              {pwRules.map((rule) => (
                <div key={rule.id} className={`auth-pw-rule ${rule.met ? "met" : ""}`}>
                  <Icon name={rule.met ? "check" : "lock"} size={12} />
                  <span>{rule.label}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <button
          type="submit"
          className="btn-pill"
          style={{ width: "100%", justifyContent: "center", marginTop: "var(--space-2)" }}
          disabled={isSubmitting}
        >
          <Icon name="shield" size={15} />
          <span>
            {isSubmitting
              ? "Verifying Credentials…"
              : mode === "login"
              ? "Sign In Securely"
              : mode === "register"
              ? "Create Client Account"
              : "Provision Staff Account"}
          </span>
        </button>
      </form>

      {config?.demoMode && mode === "login" && (
        <div className="auth-demo-box">
          <div className="auth-demo-title">
            <span>Seeded RBAC Verification Accounts (JWT Sign-In)</span>
            <Icon name="key" size={13} />
          </div>
          <div className="auth-demo-grid">
            {DEMO_ACCOUNTS.map((acct) => (
              <button
                key={acct.email}
                type="button"
                className="auth-demo-btn"
                disabled={isSubmitting}
                onClick={() => handleQuickDemoLogin(acct)}
              >
                <strong>{acct.label}</strong>
                <span>{acct.email}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function AuthModal() {
  const { ui, closeAuthModal } = useStore();
  if (!ui.authModalOpen) return null;

  return (
    <Modal
      open={ui.authModalOpen}
      onClose={closeAuthModal}
      title="Maison Authentication"
      size="md"
    >
      <AuthFormPanel
        key={ui.authModalMode}
        initialMode={ui.authModalMode || "login"}
        embedded
        onSuccess={closeAuthModal}
      />
    </Modal>
  );
}

export default AuthModal;
