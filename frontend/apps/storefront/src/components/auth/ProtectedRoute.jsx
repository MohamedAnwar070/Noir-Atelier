"use client";

import React from "react";
import { useStore } from "@/store/StoreProvider";
import { BrandMonogram } from "@/components/ui/BrandLogo";
import { Icon } from "@/components/ui/Icon";
import { ListSkeleton } from "@/components/ui/StatePanel";

export function ProtectedRoute({
  children,
  requireAuth = true,
  requireStaff = false,
  requiredRoles = [],
  requiredPermissions = [],
  title = "Maison Sign-In Required",
  description = "Please sign in with an authorized Noir Atelier profile to access this private section.",
}) {
  const {
    boot,
    isAuthenticated,
    isStaff,
    currentActor,
    hasRole,
    hasPermission,
    openAuthModal,
    navigateTo,
  } = useStore();

  if (boot.status === "loading") {
    return (
      <div className="page-container">
        <ListSkeleton count={3} />
      </div>
    );
  }

  if (requireAuth && !isAuthenticated) {
    return (
      <div className="page-container">
        <section className="protected-gate" aria-live="polite">
          <BrandMonogram size={42} />
          <span className="auth-eyebrow">Private Client &amp; Governance Access</span>
          <h1 className="auth-heading">{title}</h1>
          <p className="auth-subtitle">{description}</p>
          <div className="protected-gate-actions">
            <button
              type="button"
              className="btn-pill"
              onClick={() => openAuthModal("login")}
            >
              <Icon name="lock" size={14} />
              <span>Sign In</span>
            </button>
            <button
              type="button"
              className="btn-pill btn-pill-outline"
              onClick={() => openAuthModal(requireStaff ? "register_admin" : "register")}
            >
              <Icon name="user" size={14} />
              <span>{requireStaff ? "Staff Provisioning" : "Create Client Profile"}</span>
            </button>
            <button
              type="button"
              className="btn-pill btn-pill-outline"
              onClick={() => navigateTo("shop")}
            >
              <span>Return to Archive</span>
            </button>
          </div>
        </section>
      </div>
    );
  }

  const missingStaff = requireStaff && !isStaff;
  const missingRole = requiredRoles.length > 0 && !hasRole(...requiredRoles);
  const missingPerm =
    requiredPermissions.length > 0 &&
    !requiredPermissions.every((perm) => hasPermission(perm));

  if (missingStaff || missingRole || missingPerm) {
    return (
      <div className="page-container">
        <section className="protected-gate" role="alert" aria-live="assertive">
          <Icon name="shield" size={32} />
          <span className="auth-eyebrow">RBAC Policy Enforcement · HTTP 403</span>
          <h1 className="auth-heading">Insufficient Role Permissions</h1>
          <p className="auth-subtitle">
            Your active session is authenticated as{" "}
            <strong>{currentActor?.name || currentActor?.id}</strong>, which does not carry the
            role permissions required for this section.
          </p>
          <div className="protected-role-meta">
            Active Role: {currentActor?.role_name || currentActor?.role} ({currentActor?.role})
            {requiredPermissions.length > 0 && (
              <> · Required: {requiredPermissions.join(", ")}</>
            )}
          </div>
          <div className="protected-gate-actions">
            <button
              type="button"
              className="btn-pill"
              onClick={() => navigateTo("shop")}
            >
              <span>Explore Curated Archive</span>
            </button>
            <button
              type="button"
              className="btn-pill btn-pill-outline"
              onClick={() => navigateTo("account")}
            >
              <span>View Account Permissions</span>
            </button>
          </div>
        </section>
      </div>
    );
  }

  return <>{children}</>;
}

export default ProtectedRoute;
