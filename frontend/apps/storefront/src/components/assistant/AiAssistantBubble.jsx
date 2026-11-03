"use client";

import React, { useState, useRef, useEffect } from "react";
import { useStore } from "@/store/StoreProvider";
import { useAssistant } from "@/hooks/useAssistant";
import { Icon } from "@/components/ui/Icon";
import { formatInr, getProductImage } from "@noir/utils/formatters.js";

export function AiAssistantBubble({ onOpenProduct, onOpenBag }) {
  const { currentActor, catalog, addToBag, openDrawer, navigateTo } = useStore();
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [showTrace, setShowTrace] = useState(false);

  const {
    messages,
    isThinking,
    sendMessage,
    clearHistory,
    quickPrompts,
  } = useAssistant({
    actor: currentActor,
    onActionCompleted: (action) => {
      if (action.type === "added_to_cart") {
        // Automatically sync or notify
      }
    },
  });

  const scrollRef = useRef(null);
  const inputRef = useRef(null);

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

  return (
    <>
      {/* Floating launcher trigger (fixed bottom-right) */}
      <div className="ai-widget-container" aria-live="polite">
        {!isOpen && (
          <button
            type="button"
            className="ai-floating-trigger"
            onClick={() => setIsOpen(true)}
            aria-label="Open Noir Atelier AI Stylist Concierge"
            aria-haspopup="dialog"
            aria-expanded={false}
          >
            <span className="ai-trigger-sparkle">
              <Icon name="sparkles" size={22} />
            </span>
            <span className="ai-trigger-label">AI Stylist</span>
            <span className="ai-trigger-ping" aria-hidden="true" />
          </button>
        )}

        {/* Floating Concierge Window (Desktop card / Mobile sheet) */}
        {isOpen && (
          <section
            className="ai-assistant-card"
            role="dialog"
            aria-label="Noir Atelier AI Stylist Concierge"
            aria-modal="false"
          >
            {/* Header */}
            <header className="ai-card-header">
              <div className="ai-header-lead">
                <div className="ai-avatar-badge">
                  <Icon name="sparkles" size={16} />
                  <span className="ai-online-dot" />
                </div>
                <div>
                  <h3 className="ai-header-title">Noir Atelier Stylist</h3>
                  <p className="ai-header-subtitle">
                    4-Layer Concierge · {currentActor.label || "Customer"}
                  </p>
                </div>
              </div>
              <div className="ai-header-actions">
                <button
                  type="button"
                  className="icon-btn-subtle"
                  onClick={clearHistory}
                  title="Clear conversation"
                  aria-label="Clear conversation history"
                >
                  <Icon name="refresh" size={15} />
                </button>
                <button
                  type="button"
                  className="icon-btn-subtle"
                  onClick={() => setIsOpen(false)}
                  title="Close Assistant"
                  aria-label="Close Assistant"
                >
                  <Icon name="close" size={16} />
                </button>
              </div>
            </header>

            {/* Quick Prompts Bar */}
            <div className="ai-prompts-scroller" role="region" aria-label="Suggested questions">
              {quickPrompts.slice(0, 4).map((p, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="ai-prompt-chip"
                  onClick={() => handlePromptClick(p)}
                  disabled={isThinking}
                >
                  {p}
                </button>
              ))}
            </div>

            {/* Message Thread */}
            <div className="ai-thread" ref={scrollRef}>
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`ai-message-row ${msg.role === "user" ? "user-row" : "assistant-row"}`}
                >
                  {msg.role === "assistant" && (
                    <div className="ai-bot-avatar" aria-hidden="true">
                      <Icon name="sparkles" size={13} />
                    </div>
                  )}

                  <div className={`ai-bubble ${msg.role === "user" ? "user-bubble" : "assistant-bubble"}`}>
                    <div className="ai-bubble-text">{msg.content}</div>

                    {/* Action Feedback Card: Item Added */}
                    {msg.actionCard?.type === "item_added" && (
                      <div className="ai-action-card item-added-card">
                        <div className="ai-action-icon">
                          <Icon name="check" size={14} />
                        </div>
                        <div className="ai-action-details">
                          <div className="ai-action-title">Added to Shopping Bag</div>
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
                          <div className="ai-action-title">Order Confirmed</div>
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
                          <div className="ai-action-title">Return Claim Filed</div>
                          <div className="ai-action-sub">
                            Tier {msg.actionCard.tier || "1"} Refund · RMA pending
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

                    {/* Direct Product Recommendations inside chat */}
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
                                  {formatInr(p.price)}
                                </div>
                              </div>
                              <div className="ai-tile-actions">
                                <button
                                  type="button"
                                  className="btn-pill btn-xs"
                                  onClick={() => addToBag(p, p.sizes?.[0] || "M", 1)}
                                >
                                  + Bag
                                </button>
                                {onOpenProduct && (
                                  <button
                                    type="button"
                                    className="btn-pill btn-pill-outline btn-xs"
                                    onClick={() => onOpenProduct(p)}
                                  >
                                    View
                                  </button>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {/* Collapsible Stylist Reasoning & ReAct Steps */}
                    {Array.isArray(msg.reactSteps) && msg.reactSteps.length > 0 && (
                      <details className="ai-trace-disclosure">
                        <summary className="ai-trace-summary">
                          <span>Concierge ReAct Trace</span>
                          <span className="ai-trace-meta">
                            {msg.reactSteps.length} steps · {msg.agentName || "supervisor"}
                          </span>
                        </summary>
                        <div className="ai-trace-content">
                          {msg.reactSteps.map((step, idx) => (
                            <div key={idx} className="ai-trace-step">
                              <span className="step-tag">{step.tag || `STEP ${idx + 1}`}</span>
                              <span className="step-body">{step.content || step.detail}</span>
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

              {/* Thinking Indicator */}
              {isThinking && (
                <div className="ai-message-row assistant-row">
                  <div className="ai-bot-avatar" aria-hidden="true">
                    <Icon name="sparkles" size={13} />
                  </div>
                  <div className="ai-bubble assistant-bubble ai-typing-bubble">
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                  </div>
                </div>
              )}
            </div>

            {/* Input Form */}
            <form className="ai-input-form" onSubmit={handleSend}>
              <input
                ref={inputRef}
                type="text"
                className="ai-text-input"
                placeholder="Ask about tailored garments, linen, sizes, returns…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={isThinking}
                aria-label="Stylist query"
              />
              <button
                type="submit"
                className="ai-send-btn"
                disabled={!input.trim() || isThinking}
                aria-label="Send message"
              >
                <Icon name="arrow-right" size={16} />
              </button>
            </form>
          </section>
        )}
      </div>
    </>
  );
}
