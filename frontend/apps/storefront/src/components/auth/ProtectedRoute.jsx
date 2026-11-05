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
          <span className="auth-eyebrow">Maison Private Client Suite</span>
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
              <span>Explore The Archive</span>
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
          <Icon name="shield" size={36} />
          <span className="auth-eyebrow">Private Atelier Access</span>
          <h1 className="auth-heading">Atelier Staff Access Restricted</h1>
          <p className="auth-subtitle">
            This section is reserved for authorized Noir Atelier curatorial staff and store directors.
            If you are a member of our team, please sign in with your administrative profile.
          </p>
          <div className="protected-gate-actions">
            <button
              type="button"
              className="btn-pill"
              onClick={() => openAuthModal("login")}
            >
              <Icon name="lock" size={14} />
              <span>Sign In with Staff Account</span>
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

  return <>{children}</>;
}

export default ProtectedRoute;
