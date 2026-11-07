"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NoirApiClient } from "@noir/api/client.js";
import { ASSISTANT, LIMITS } from "@/config/ui.config";
import { friendlyErrorMessage } from "@noir/ui/states.js";
import { normalizeProduct } from "@/store/normalizers";

const SESSION_KEY = "noir_chat_session";

/** Unguessable per-tab chat session id (the server binds its history to the signed-in shopper). */
function newSessionId() {
  const random =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID().replace(/-/g, "")
      : Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join("");
  return `SES-${random.toUpperCase()}`;
}

function resolveSessionId() {
  try {
    const existing = typeof window !== "undefined" ? window.sessionStorage.getItem(SESSION_KEY) : null;
    if (existing && existing.length >= 20) return existing;
    const created = newSessionId();
    if (typeof window !== "undefined") window.sessionStorage.setItem(SESSION_KEY, created);
    return created;
  } catch {
    return newSessionId();
  }
}

function rememberSessionId(sessionId) {
  try {
    if (sessionId && typeof window !== "undefined") window.sessionStorage.setItem(SESSION_KEY, sessionId);
  } catch {
    /* storage unavailable: the server issues a fresh session next time */
  }
}

let messageCounter = 0;
const nextId = () => `m-${Date.now()}-${messageCounter++}`;

export function useAssistant({
  api,
  actor,
  businessConfig,
  isStaff = false,
  onAfterAction,
  onActionCompleted,
} = {}) {
  const [messages, setMessages] = useState([
    {
      id: "welcome-msg",
      role: "assistant",
      content: ASSISTANT.welcome,
      timestamp: Date.now(),
    },
  ]);
  const [busy, setBusy] = useState(false);
  // Live progress from the streamed turn (e.g. "Searching the collection…").
  const [statusLabel, setStatusLabel] = useState("");
  const busyRef = useRef(false);

  const clientRef = useRef(api || null);
  if (!clientRef.current) {
    clientRef.current = new NoirApiClient({ token: actor?.token });
  }

  useEffect(() => {
    if (actor?.token) {
      clientRef.current.setToken(actor.token);
    }
  }, [actor?.token]);

  const quickPrompts = useMemo(() => {
    const rawPrompts = businessConfig?.storefront_ui?.ai_quick_prompts || [];
    return rawPrompts
      .filter((item) => {
        if (!item) return false;
        if (typeof item === "string") return true;
        if (item.audience === "staff" && !isStaff) return false;
        return Boolean(item.prompt || item.label);
      })
      .map((item) =>
        typeof item === "string"
          ? { label: item, prompt: item }
          : { label: item.label || item.prompt, prompt: item.prompt || item.label }
      );
  }, [businessConfig, isStaff]);

  const send = useCallback(
    async (rawText) => {
      const text = String(rawText || "").trim().slice(0, LIMITS?.chatMaxLength || 500);
      if (!text || busyRef.current) return;

      busyRef.current = true;
      setBusy(true);

      const userMsg = {
        id: nextId(),
        role: "user",
        content: text,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);

      try {
        const client = api || clientRef.current;
        const res = await client.chatWithAgentsStream({
          message: text,
          customerId: actor?.role === "customer" ? (actor.id || actor.customerId || null) : null,
          actorRole: actor?.role || "customer",
          sessionId: resolveSessionId(),
          onStatus: setStatusLabel,
        });

        rememberSessionId(res.session_id);
        const feedback = res.action_feedback || null;
        let actionCard = null;

        if (feedback) {
          if (feedback.action === "order_placed") {
            actionCard = {
              type: "order_placed",
              orderId: feedback.details?.order_id || "ORD-NEW",
              grandTotal: feedback.details?.grand_total_inr ?? feedback.details?.grand_total,
            };
          } else if (feedback.action === "cart_updated") {
            actionCard = {
              type: "item_added",
              name: feedback.details?.name || feedback.summary,
              productId: feedback.details?.product_id,
              size: feedback.details?.size,
              quantity: feedback.details?.quantity,
            };
          } else if (feedback.action === "return_submitted") {
            actionCard = {
              type: "return_initiated",
              tier: feedback.details?.refund_tier || "1",
            };
          }
        }

        const agentMsg = {
          id: nextId(),
          role: "assistant",
          content: res.reply || "I couldn't put an answer together just now. Please try again.",
          status: res.status,
          persona: res.persona || ASSISTANT.name,
          referenceId: res.reference_id || null,
          actionCard,
          actionFeedback: feedback,
          stylistMode: res.stylist_mode || null,
          stylistNotes: Array.isArray(res.stylist_notes) ? res.stylist_notes : [],
          followUpPrompts: Array.isArray(res.follow_up_prompts) ? res.follow_up_prompts : [],
          totalMrpInr: res.total_mrp_inr || null,
          // Normalized like catalog products so tiles show the same per-size price range
          productCards: Array.isArray(res.products) ? res.products.slice(0, 6).map(normalizeProduct) : [],
          timestamp: Date.now(),
        };

        setMessages((prev) => [...prev, agentMsg]);
        await onAfterAction?.(res);
        await onActionCompleted?.(actionCard || res);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "assistant",
            content: friendlyErrorMessage(err, "I couldn't reach the atelier just now. Please try again in a moment."),
            timestamp: Date.now(),
          },
        ]);
      } finally {
        busyRef.current = false;
        setBusy(false);
        setStatusLabel("");
      }
    },
    [api, actor, onAfterAction, onActionCompleted]
  );

  const reset = useCallback(() => {
    setMessages([
      {
        id: "welcome-msg",
        role: "assistant",
        content: ASSISTANT.welcome,
        timestamp: Date.now(),
      },
    ]);
  }, []);

  return {
    messages,
    busy,
    isThinking: busy,
    statusLabel,
    send,
    sendMessage: send,
    reset,
    clear: reset,
    clearHistory: reset,
    quickPrompts,
  };
}
