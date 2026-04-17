"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import AlertCard from "./AlertCard";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8001";

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
  violation_type?: string;
  ppe_detail?: Record<string, number>;
  false_positive?: boolean;
  persons_count?: number;
  person_name?: string;
  uniform_code?: string;
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
      if (!audioCtxRef.current) audioCtxRef.current = new AudioContext();
      const ctx = audioCtxRef.current;
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.connect(gain); gain.connect(ctx.destination);
      oscillator.frequency.value = isHigh ? 880 : 440;
      gain.gain.value = isHigh ? 0.5 : 0.3;
      oscillator.type = "square";
      oscillator.start();
      oscillator.stop(ctx.currentTime + (isHigh ? 0.5 : 0.3));
    } catch { /* audio not available */ }
  }, []);

  const connectWs = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    const ws = new WebSocket(`${WS_URL}/ws/alerts`);
    ws.onopen = () => {
      setConnected(true);
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send("ping");
        else clearInterval(pingInterval);
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
          if (alert.shutdown_triggered) onShutdown(alert);
        }
      } catch { /* pong or non-json */ }
    };
    ws.onclose = () => { setConnected(false); reconnectRef.current = setTimeout(connectWs, 3000); };
    ws.onerror = () => { ws.close(); };
    wsRef.current = ws;
  }, [onAlert, onShutdown, playBeep]);

  useEffect(() => {
    connectWs();
    return () => { if (reconnectRef.current) clearTimeout(reconnectRef.current); wsRef.current?.close(); };
  }, [connectWs]);

  const resolveAlert = async (alertId: number) => {
    try {
      await fetch(`${API_URL}/alerts/${alertId}/resolve`, { method: "POST" });
      setAlerts((prev) => prev.map((a) => a.alert_id === alertId ? { ...a, resolved: true } : a));
    } catch (err) { console.error("Failed to resolve", err); }
  };

  const markFalsePositive = async (alertId: number) => {
    try {
      await fetch(`${API_URL}/alerts/${alertId}/false-positive`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}),
      });
      setAlerts((prev) => prev.map((a) => a.alert_id === alertId ? { ...a, false_positive: true, resolved: true } : a));
    } catch (err) { console.error("Failed to mark false positive", err); }
  };

  const unresolvedCount = alerts?.filter?.((a) => !a.resolved)?.length || 0;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-[#162033] shrink-0">
        <div className="flex items-center justify-between">
          <h2 className="text-[10px] font-bold text-white tracking-[0.15em] uppercase flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-red-500/10 border border-red-500/20 flex items-center justify-center">
              <svg className="w-3 h-3 text-red-400" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
              </svg>
            </div>
            Log Alert
          </h2>
          <div className="flex items-center gap-2">
            {unresolvedCount > 0 && (
              <span className="text-[9px] font-bold text-white bg-red-500 px-1.5 py-0.5 rounded-md min-w-[18px] text-center">
                {unresolvedCount}
              </span>
            )}
            <div className={`status-dot ${connected ? "online" : "offline"}`} />
          </div>
        </div>
      </div>

      {/* Alert List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {(alerts?.length || 0) === 0 ? (
          <div className="text-center py-16 text-industrial-600">
            <svg className="w-10 h-10 mx-auto mb-3 opacity-15" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z" />
            </svg>
            <p className="text-[10px] font-bold uppercase tracking-wider">Area Secured</p>
          </div>
        ) : (
          alerts?.map?.((alert, idx) => (
            <AlertCard key={`${alert.alert_id || idx}-${idx}`} alert={alert} onResolve={resolveAlert} onFalsePositive={markFalsePositive} />
          ))
        )}
      </div>
    </div>
  );
}
