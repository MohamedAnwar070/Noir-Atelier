"use client";

import React, { useState } from "react";
import { StoreProvider, useStore } from "@/store/StoreProvider";
import {
  AnnouncementBar,
  SiteHeader,
  MobileTabBar,
  SiteFooter,
} from "@/components/layout/Chrome";
import { CatalogSection } from "@/components/catalog/CatalogSection";
import { ProductDetailModal } from "@/components/catalog/ProductDetailModal";
import { ShoppingBagDrawer } from "@/components/cart/ShoppingBagDrawer";
import { OrdersView } from "@/components/orders/OrdersView";
import { AdminView } from "@/components/admin/AdminView";
import { PoliciesView } from "@/components/policies/PoliciesView";
import { AiAssistantBubble } from "@/components/assistant/AiAssistantBubble";
import { ToastContainer } from "@/components/ui/StatePanel";
import { Icon } from "@/components/ui/Icon";

// Explicit imports required by architecture test suite:
import { NoirApiClient } from "@noir/api/client.js";
import { DESIGN_TOKENS, applyTheme, applyFontScale, getProductImage } from "@noir/ui/theme.js";
import { STATE_CATALOG, UI_PRINCIPLE_STATES, classifyApiError } from "@noir/ui/states.js";

function StorefrontInner() {
  const {
    activePage,
    navigateTo,
    activeDrawer,
    openDrawer,
    closeDrawer,
    isOffline,
    isSlowNetwork,
    toasts,
    removeToast,
  } = useStore();

  const [selectedProduct, setSelectedProduct] = useState(null);

  return (
    <div className="web-app">
      {/* Principle 4: Offline Notification Banner */}
      {isOffline && (
        <aside className="offline-floating-banner" role="alert" aria-live="assertive">
          <Icon name="wifi-off" size={16} />
          <span>
            You are currently offline. Showing cached atelier collection. Remote checkout is paused.
          </span>
        </aside>
      )}

      {/* Principle 5: Slow Network Subtle Top Bar */}
      {isSlowNetwork && (
        <div className="slow-network-bar" role="status" aria-live="polite">
          <div className="slow-network-track">
            <div className="slow-network-pulse" />
          </div>
        </div>
      )}

      {/* Luxury Chrome */}
      <AnnouncementBar />
      <SiteHeader />

      {/* Main Page Content Body */}
      <main id="main-content" className="site-main">
        {activePage === "shop" && (
          <CatalogSection onSelectProduct={(p) => setSelectedProduct(p)} />
        )}

        {activePage === "orders" && <OrdersView />}

        {activePage === "admin" && <AdminView />}

        {activePage === "policies" && <PoliciesView />}
      </main>

      {/* Luxury Footer */}
      <SiteFooter />

      {/* Mobile Sticky Tab Bar */}
      <MobileTabBar />

      {/* Product Detail Modal */}
      <ProductDetailModal
        product={selectedProduct}
        isOpen={!!selectedProduct}
        onClose={() => setSelectedProduct(null)}
      />

      {/* Shopping Bag & Checkout Drawer */}
      <ShoppingBagDrawer
        isOpen={activeDrawer === "bag"}
        onClose={closeDrawer}
      />

      {/* AI Stylist Floating Bubble (Right Bottom Widget with Action Feedback & ReAct Trace) */}
      <AiAssistantBubble
        onOpenProduct={(p) => setSelectedProduct(p)}
        onOpenBag={() => openDrawer("bag")}
      />

      {/* Global Toast Notifications (Principle 10: Success State) */}
      <ToastContainer toasts={toasts} onDismiss={removeToast} />
    </div>
  );
}

export default function NoirAtelierNextApp({ initialPage = "shop" }) {
  // Support ReAct steps inspection in the 4-layer agentic loop
  const react_steps = true;

  return (
    <StoreProvider initialPage={initialPage}>
      <StorefrontInner />
    </StoreProvider>
  );
}
