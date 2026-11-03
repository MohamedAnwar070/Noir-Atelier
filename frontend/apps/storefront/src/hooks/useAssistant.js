"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NoirApiClient } from "@noir/api/client.js";
import { ASSISTANT, LIMITS } from "@/config/ui.config";
import { friendlyErrorMessage } from "@noir/ui/states.js";
import { normalizeProduct } from "@/store/normalizers";

const SESSION_KEY = "noir_chat_session";

function resolveSessionId() {
  try {
    const existing = typeof window !== "undefined" ? window.sessionStorage.getItem(SESSION_KEY) : null;
    if (existing) return existing;
    const created = `SES-${Math.random().toString(36).slice(2, 10).toUpperCase()}`;
    if (typeof window !== "undefined") window.sessionStorage.setItem(SESSION_KEY, created);
    return created;
  } catch {
    return `SES-${Date.now().toString(36).toUpperCase()}`;
  }
}

let messageCounter = 0;
const nextId = () => `m-${Date.now()}-${messageCounter++}`;

export function useAssistant({
  api,
  actor,
  businessConfig,
  agentRegistry = [],
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

  const personaByAgent = useMemo(() => {
    const map = {};
    for (const entry of agentRegistry || []) {
      if (entry?.agent_name) {
        map[entry.agent_name] = entry.persona || entry.agent_name;
      }
    }
    return map;
  }, [agentRegistry]);

  const quickPrompts = useMemo(() => {
    const rawPrompts = businessConfig?.storefront_ui?.ai_quick_prompts || [];
    return rawPrompts
      .filter((item) => {
        if (!item) return false;
        if (typeof item === "string") return true;
        if (item.audience === "staff" && !isStaff) return false;
        return Boolean(item.prompt || item.label);
      })
      .map((item) => (typeof item === "string" ? item : item.prompt || item.label));
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
        const res = await client.chatWithAgents({
          message: text,
          customerId: actor?.role === "customer" ? (actor.id || actor.customerId || "CUS-001") : null,
          actorRole: actor?.role || "customer",
          sessionId: resolveSessionId(),
        });

        const feedback = res.data?.action_feedback || null;
        let actionCard = null;

        if (feedback) {
          if (feedback.action === "order_placed" || res.routed_agent === "order_agent") {
            actionCard = {
              type: "order_placed",
              orderId: feedback.details?.order_id || res.data?.order?.order_id || "ORD-NEW",
              grandTotal: feedback.details?.grand_total_inr ?? res.data?.order?.grand_total_inr ?? feedback.details?.grand_total,
            };
          } else if (feedback.action === "cart_updated" || res.routed_agent === "cart_agent") {
            actionCard = {
              type: "item_added",
              name: feedback.details?.name || feedback.summary,
              productId: feedback.details?.product_id,
              size: feedback.details?.size,
              quantity: feedback.details?.quantity,
            };
          } else if (feedback.action === "return_submitted" || res.routed_agent === "returns_agent") {
            actionCard = {
              type: "return_initiated",
              tier: feedback.details?.refund_tier || "1",
            };
          }
        }

        const agentMsg = {
          id: nextId(),
          role: "assistant",
          content: res.reply || "I have coordinated with our atelier agents.",
          status: res.status,
          persona: personaByAgent[res.routed_agent] || ASSISTANT.name,
          actionCard,
          // Normalized like catalog products so tiles show the same per-size price range
          productCards: Array.isArray(res.data?.products) ? res.data.products.slice(0, 4).map(normalizeProduct) : [],
          reactSteps: res.react_steps || [],
          agentName: res.routed_agent || "supervisor",
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
      }
    },
    [api, actor, personaByAgent, onAfterAction, onActionCompleted]
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
    send,
    sendMessage: send,
    reset,
    clear: reset,
    clearHistory: reset,
    quickPrompts,
  };
}
