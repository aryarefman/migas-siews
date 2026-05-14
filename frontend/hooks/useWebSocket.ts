"use client";

import { useEffect, useRef, useCallback, useState } from "react";

export type WsStatus = "connecting" | "connected" | "disconnected" | "error";

interface UseWebSocketOptions {
  url: string;
  onMessage?: (data: unknown) => void;
  onStatusChange?: (status: WsStatus) => void;
  /** Max delay between reconnect attempts in ms. Default: 30000 */
  maxDelay?: number;
  /** Ping interval in ms to keep connection alive. Default: 30000 */
  pingInterval?: number;
  /** Whether to auto-reconnect. Default: true */
  autoReconnect?: boolean;
}

export function useWebSocket({
  url,
  onMessage,
  onStatusChange,
  maxDelay = 30_000,
  pingInterval = 30_000,
  autoReconnect = true,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const attemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);
  const [status, setStatus] = useState<WsStatus>("connecting");

  const setStatusSafe = useCallback(
    (s: WsStatus) => {
      if (!mountedRef.current) return;
      setStatus(s);
      onStatusChange?.(s);
    },
    [onStatusChange]
  );

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatusSafe("connecting");

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      attemptsRef.current = 0;
      setStatusSafe("connected");

      // Ping to keep alive
      pingTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
        else clearInterval(pingTimerRef.current!);
      }, pingInterval);
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const data = JSON.parse(event.data);
        onMessage?.(data);
      } catch {
        // pong or non-JSON — ignore
      }
    };

    ws.onerror = () => {
      setStatusSafe("error");
      ws.close();
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      clearTimers();
      setStatusSafe("disconnected");

      if (!autoReconnect) return;

      // Exponential backoff: 1s, 2s, 4s, 8s … capped at maxDelay
      const delay = Math.min(maxDelay, 1_000 * Math.pow(2, attemptsRef.current));
      attemptsRef.current += 1;
      console.log(`[WS] Reconnecting in ${delay}ms (attempt ${attemptsRef.current})`);
      reconnectTimerRef.current = setTimeout(connect, delay);
    };
  }, [url, onMessage, pingInterval, autoReconnect, maxDelay, setStatusSafe, clearTimers]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimers();
      wsRef.current?.close();
    };
  }, [connect, clearTimers]);

  const send = useCallback((data: string | object) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(typeof data === "string" ? data : JSON.stringify(data));
  }, []);

  return { status, send, attempts: attemptsRef.current };
}
