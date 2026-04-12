"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import AlertCard from "./AlertCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

interface AlertData {
  alert_id: number;
  zone_name: string;
  zone_id: number;
  risk_level: string;
  timestamp: string;
  confidence: number;
  snapshot_url: string;
  shutdown_triggered: boolean;
  resolved?: boolean;
}

interface AlertFeedProps {
  onAlert: (alert: AlertData) => void;
  onShutdown: (alert: AlertData) => void;
}

export default function AlertFeed({ onAlert, onShutdown }: AlertFeedProps) {
  const [alerts, setAlerts] = useState<AlertData[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<NodeJS.Timeout | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);

  const playBeep = useCallback((isHigh: boolean) => {
    try {
      if (!audioCtxRef.current) {
        audioCtxRef.current = new AudioContext();
      }
      const ctx = audioCtxRef.current;
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.connect(gain);
      gain.connect(ctx.destination);
      oscillator.frequency.value = isHigh ? 880 : 440;
      gain.gain.value = isHigh ? 0.5 : 0.3;
      oscillator.type = "square";
      oscillator.start();
      oscillator.stop(ctx.currentTime + (isHigh ? 0.5 : 0.3));
    } catch {
      /* audio not available */
    }
  }, []);

  const connectWs = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`${WS_URL}/ws/alerts`);

    ws.onopen = () => {
      console.log("[WS] Connected");
      setConnected(true);
      // Ping to keep alive
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send("ping");
        } else {
          clearInterval(pingInterval);
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "alert") {
          const alert: AlertData = data;
          setAlerts((prev) => [alert, ...prev].slice(0, 30));
          playBeep(alert.risk_level === "high");
          onAlert(alert);
          if (alert.shutdown_triggered) {
            onShutdown(alert);
          }
        }
      } catch {
        /* pong or non-json */
      }
    };

    ws.onclose = () => {
      console.log("[WS] Disconnected, reconnecting...");
      setConnected(false);
      reconnectRef.current = setTimeout(connectWs, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };

    wsRef.current = ws;
  }, [onAlert, onShutdown, playBeep]);

  useEffect(() => {
    connectWs();
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connectWs]);

  const resolveAlert = async (alertId: number) => {
    try {
      await fetch(`${API_URL}/alerts/${alertId}/resolve`, { method: "POST" });
      setAlerts((prev) =>
        prev.map((a) =>
          a.alert_id === alertId ? { ...a, resolved: true } : a
        )
      );
    } catch (err) {
      console.error("Failed to resolve alert", err);
    }
  };

  const unresolvedCount = alerts.filter((a) => !a.resolved).length;

  return (
    <div className="glass-card flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-industrial-800 shrink-0">
        <div className="flex items-center justify-between">
          <h2 className="text-[10px] font-black text-white tracking-[0.2em] uppercase flex items-center gap-2">
            <svg className="w-3.5 h-3.5 text-red-600" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
            </svg>
            Log Alert
          </h2>
          <div className="flex items-center gap-2">
            {unresolvedCount > 0 && (
              <span className="text-[10px] font-black text-white bg-red-600 px-1.5 py-0.5">
                {unresolvedCount}
              </span>
            )}
            <div
              className={`w-2 h-2 ${
                connected ? "bg-emerald-500" : "bg-red-500"
              }`}
            />
          </div>
        </div>
      </div>

      {/* Alert List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {alerts.length === 0 ? (
          <div className="text-center py-12 text-industrial-600">
            <svg className="w-10 h-10 mx-auto mb-3 opacity-20" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/>
            </svg>
            <p className="text-[10px] font-black uppercase tracking-widest">Area Secured</p>
          </div>
        ) : (
          alerts.map((alert, idx) => (
            <AlertCard
              key={`${alert.alert_id}-${idx}`}
              alert={alert}
              onResolve={resolveAlert}
            />
          ))
        )}
      </div>
    </div>
  );
}
