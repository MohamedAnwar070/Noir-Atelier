"use client";

import React, { useState, useRef, useEffect } from "react";
import { useStore } from "@/store/StoreProvider";
import { Icon } from "@/components/ui/Icon";
import { BrandMonogram } from "@/components/ui/BrandLogo";
import { ASSISTANT } from "@/config/ui.config";
import { formatInr, formatPriceRange, getProductImage } from "@noir/utils/formatters.js";

const CURATED_PROMPTS = [
  { label: "Haute Archive (₹1L+)", prompt: "Show me Haute Archive couture garments above INR 100000" },
  { label: "Himalayan Cashmere", prompt: "Show me Himalayan cashmere and fine wool garments" },
  { label: "Mulberry Silk Edit", prompt: "Show me mulberry silk dresses, skirts, and eveningwear" },
  { label: "Wardrobe Guidance", prompt: "What are your top recommendations for a timeless luxury capsule wardrobe?" },
  { label: "Sizing & Tailoring", prompt: "How does Noir Atelier sizing work and what tailoring alterations are supported?" },
  { label: "Delivery & Returns", prompt: "What are the boutique delivery options, white-glove couriers, and 7-day return policies?" },
];

export function AiAssistantBubble({ onOpenProduct, onOpenBag }) {
  const { assistant, addToBag, openDrawer, navigateTo, ui, setOverlay } = useStore();
  const [input, setInput] = useState("");

  const isOpen = Boolean(ui?.chatOpen);
  const setIsOpen = (nextOpen) => setOverlay({ chatOpen: Boolean(nextOpen) });

  const {
    messages,
    isThinking,
    sendMessage,
    clearHistory,
    quickPrompts,
  } = assistant;

  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  // Close with Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        inputRef.current?.focus();
        if (scrollRef.current) {
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
      }, 100);
    }
  }, [isOpen, messages, isThinking]);

  const handleSend = (e) => {
    e?.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isThinking) return;
    setInput("");
    sendMessage(trimmed);
  };

  const handlePromptClick = (prompt) => {
    if (isThinking) return;
    sendMessage(prompt);
  };

  const promptList = (quickPrompts && quickPrompts.length > 0) ? quickPrompts : CURATED_PROMPTS;

  return (
    <>
      {/* Backdrop overlay for quick dismissal on all screen sizes */}
      {isOpen && (
        <div
          className="ai-card-backdrop"
          onClick={() => setIsOpen(false)}
          aria-hidden="true"
        />
      )}

      <div className="ai-widget-container" aria-live="polite">
        {!isOpen && (
          <button
            type="button"
            className="ai-floating-trigger"
            onClick={() => setIsOpen(true)}
            aria-label="Open Noir Atelier Personal Fashion Consultant"
            aria-haspopup="dialog"
            aria-expanded={false}
          >
            <span className="ai-trigger-sparkle" aria-hidden="true">
              <BrandMonogram size={22} reversed />
            </span>
            <span className="ai-trigger-label">Personal Stylist</span>
            <span className="ai-trigger-ping" aria-hidden="true" />
          </button>
        )}

        {isOpen && (
          <section
            className="ai-assistant-card"
            role="dialog"
            aria-label="Noir Atelier Personal Fashion Consultant"
            aria-modal="true"
          >
            {/* Sheet Grabber for Mobile Drawers */}
            <div
              className="ai-sheet-grabber"
              onClick={() => setIsOpen(false)}
              role="button"
              aria-label="Dismiss consultation drawer"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  setIsOpen(false);
                }
              }}
            />

            {/* Header */}
            <header className="ai-card-header">
              <div className="ai-header-lead">
                <div className="ai-avatar-badge" aria-hidden="true">
                  <BrandMonogram size={24} reversed />
                  <span className="ai-online-dot" />
                </div>
                <div className="ai-header-text">
                  <h3 className="ai-header-title">{ASSISTANT.name}</h3>
                  <p className="ai-header-subtitle">
                    <span className="ai-pulse-dot" /> Grounded in 100-Piece Atelier Archive
                  </p>
                </div>
              </div>
              <div className="ai-header-actions">
                <button
                  type="button"
                  className="ai-header-btn"
                  onClick={clearHistory}
                  title="Start new consultation"
                  aria-label="Start new consultation"
                >
                  <Icon name="refresh" size={13} />
                  <span className="ai-btn-text">Reset</span>
                </button>
                <button
                  type="button"
                  className="ai-header-btn ai-close-btn"
                  onClick={() => setIsOpen(false)}
                  title="Close consultation (Esc)"
                  aria-label="Close consultation"
                >
                  <Icon name="close" size={15} />
                  <span className="ai-btn-text">Close</span>
                </button>
              </div>
            </header>

            {/* Curated Consultation Quick Suggestions */}
            {promptList.length > 0 && (
              <div className="ai-prompts-scroller" role="region" aria-label="Suggested consultations">
                {promptList.slice(0, 6).map((item, idx) => {
                  const label = typeof item === "string" ? item : (item.label || item.prompt);
                  const prompt = typeof item === "string" ? item : (item.prompt || item.label);
                  return (
                    <button
                      key={idx}
                      type="button"
                      className="ai-prompt-chip"
                      onClick={() => handlePromptClick(prompt)}
                      disabled={isThinking}
                      title={prompt}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            )}

            {/* Message Thread */}
            <div className="ai-thread" ref={scrollRef}>
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`ai-message-row ${msg.role === "user" ? "user-row" : "assistant-row"}`}
                >
                  {msg.role === "assistant" && (
                    <div className="ai-bot-avatar" aria-hidden="true">
                      <BrandMonogram size={17} reversed />
                    </div>
                  )}

                  <div className={`ai-bubble ${msg.role === "user" ? "user-bubble" : "assistant-bubble"}`}>
                    {msg.role === "assistant" && msg.persona && (
                      <div className="ai-persona-label">
                        {msg.persona}
                      </div>
                    )}
                    <div className="ai-bubble-text">{msg.content}</div>

                    {/* Action Feedback Card: Item Added */}
                    {msg.actionCard?.type === "item_added" && (
                      <div className="ai-action-card item-added-card">
                        <div className="ai-action-icon">
                          <Icon name="check" size={14} />
                        </div>
                        <div className="ai-action-details">
                          <div className="ai-action-title">Placed in Shopping Bag</div>
                          <div className="ai-action-sub">
                            {msg.actionCard.name || msg.actionCard.productId}
                            {msg.actionCard.size ? ` · Size ${msg.actionCard.size}` : ""}
                            {msg.actionCard.quantity ? ` × ${msg.actionCard.quantity}` : ""}
                          </div>
                        </div>
                        <button
                          type="button"
                          className="btn-pill btn-pill-outline btn-xs"
                          onClick={() => {
                            if (onOpenBag) onOpenBag();
                            else openDrawer("bag");
                          }}
                        >
                          View Bag
                        </button>
                      </div>
                    )}

                    {/* Action Feedback Card: Order Confirmed */}
                    {msg.actionCard?.type === "order_placed" && (
                      <div className="ai-action-card order-confirmed-card">
                        <div className="ai-action-icon success">
                          <Icon name="package" size={14} />
                        </div>
                        <div className="ai-action-details">
                          <div className="ai-action-title">Acquisition Confirmed</div>
                          <div className="ai-action-sub">
                            Ref #{msg.actionCard.orderId}
                            {msg.actionCard.grandTotal
                              ? ` · ${formatInr(msg.actionCard.grandTotal)}`
                              : ""}
                          </div>
                        </div>
                        <button
                          type="button"
                          className="btn-pill btn-pill-outline btn-xs"
                          onClick={() => navigateTo("orders")}
                        >
                          View Orders
                        </button>
                      </div>
                    )}

                    {/* Action Feedback Card: Return Initiated */}
                    {msg.actionCard?.type === "return_initiated" && (
                      <div className="ai-action-card return-card">
                        <div className="ai-action-icon info">
                          <Icon name="shield" size={14} />
                        </div>
                        <div className="ai-action-details">
                          <div className="ai-action-title">Return Dossier Filed</div>
                          <div className="ai-action-sub">
                            Tier {msg.actionCard.tier || "1"} Refund · RMA registered
                          </div>
                        </div>
                        <button
                          type="button"
                          className="btn-pill btn-pill-outline btn-xs"
                          onClick={() => navigateTo("orders")}
                        >
                          Track Return
                        </button>
                      </div>
                    )}

                    {/* Direct Archive Product Cards inside Consultation */}
                    {Array.isArray(msg.productCards) && msg.productCards.length > 0 && (
                      <div className="ai-product-carousel">
                        {msg.productCards.map((p) => {
                          const img = getProductImage(p);
                          return (
                            <div key={p.product_id} className="ai-product-tile">
                              {img.url ? (
                                <img
                                  src={img.url}
                                  alt={img.alt}
                                  className="ai-tile-thumb"
                                  loading="lazy"
                                />
                              ) : (
                                <div className="ai-tile-thumb placeholder" />
                              )}
                              <div className="ai-tile-info">
                                <div className="ai-tile-name">{p.name}</div>
                                <div className="ai-tile-price">
                                  {formatPriceRange(p)}
                                </div>
                              </div>
                              <div className="ai-tile-actions">
                                <button
                                  type="button"
                                  className="btn-pill btn-xs"
                                  onClick={() => addToBag(p, p.sizes_available?.[0], 1)}
                                >
                                  + Bag
                                </button>
                                {onOpenProduct && (
                                  <button
                                    type="button"
                                    className="btn-pill btn-pill-outline btn-xs"
                                    onClick={() => {
                                      setIsOpen(false);
                                      onOpenProduct(p);
                                    }}
                                  >
                                    Dossier
                                  </button>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* Collapsible Grounded Archive & Governance Trace */}
                    {Array.isArray(msg.reactSteps) && msg.reactSteps.length > 0 && (
                      <details className="ai-trace-disclosure">
                        <summary className="ai-trace-summary">
                          <span>Verified Archive &amp; Policy Trace</span>
                          <span className="ai-trace-meta">
                            {msg.reactSteps.length} checks · {msg.agentName || "consultant"}
                          </span>
                        </summary>
                        <div className="ai-trace-content">
                          {msg.reactSteps.map((step, idx) => (
                            <div key={idx} className="ai-trace-step">
                              <span className="step-tag">{step.tag || step.layer || `STEP ${idx + 1}`}</span>
                              <span className="step-body">{step.content || step.thought || step.detail}</span>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}

                    <span className="ai-bubble-time">
                      {new Date(msg.timestamp).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                </div>
              ))}

              {isThinking && (
                <div className="ai-message-row assistant-row">
                  <div className="ai-bot-avatar" aria-hidden="true">
                    <BrandMonogram size={17} reversed />
                  </div>
                  <div className="ai-bubble assistant-bubble ai-typing-bubble">
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                  </div>
                </div>
              )}
            </div>

            {/* Input Form with Ergonomic Controls */}
            <div className="ai-footer-bar">
              <form className="ai-input-form" onSubmit={handleSend}>
                <div className="ai-input-wrapper">
                  <input
                    ref={inputRef}
                    type="text"
                    className="ai-text-input"
                    placeholder={ASSISTANT.inputPlaceholder}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    disabled={isThinking}
                    aria-label="Consultation query"
                  />
                  {input && (
                    <button
                      type="button"
                      className="ai-input-clear-btn"
                      onClick={() => setInput("")}
                      aria-label="Clear input text"
                    >
                      <Icon name="close" size={12} />
                    </button>
                  )}
                </div>
                <button
                  type="submit"
                  className="ai-send-btn"
                  disabled={!input.trim() || isThinking}
                  aria-label="Send inquiry"
                  title="Send (Enter)"
                >
                  <Icon name="arrow-right" size={16} />
                </button>
              </form>
              <div className="ai-input-hint">
                Press Enter to send · Live Natural Fiber &amp; Sizing Intelligence
              </div>
            </div>
          </section>
        )}
      </div>
    </>
  );
}
