"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import AlertCard from "./AlertCard";
import DetailPanel from "./DetailPanel";
import { showToast } from "./Toast";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8001";
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

/**
 * Plays a notification sound using the Web Audio API.
 * High risk alerts get a double beep, low risk get a single beep.
 */
function playNotificationSound(isHighRisk: boolean) {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    
    const playBeep = (freq: number, duration: number, startTime: number) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, startTime);
      
      gain.gain.setValueAtTime(0, startTime);
      gain.gain.linearRampToValueAtTime(0.2, startTime + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.01, startTime + duration);
      
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      
      osc.start(startTime);
      osc.stop(startTime + duration);
    };

    const now = audioCtx.currentTime;
    if (isHighRisk) {
      // Urgent double beep (880Hz -> A5)
      playBeep(880, 0.15, now);
      playBeep(880, 0.15, now + 0.2);
    } else {
      // Info beep (440Hz -> A4)
      playBeep(440, 0.2, now);
    }
  } catch (e) {
    console.warn("Audio alert failed:", e);
  }
}

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
  false_positive?: boolean;
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
  const [selectedAlert, setSelectedAlert] = useState<AlertData | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<NodeJS.Timeout | null>(null);

  const connectWs = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const timeout = setTimeout(() => {
      try {
        const ws = new WebSocket(`${WS_URL}/ws/alerts`);

        ws.onopen = () => {
          setConnected(true);
          // Keep-alive ping
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
              onAlert(alert);
              if (alert.shutdown_triggered) onShutdown(alert);
              
              // Toast notification
              const violationType = alert.violation_type || "";
              let message = "";
              let type: "success" | "error" | "info" = "error";

              if (violationType === "fire_smoke") {
                message = `🔥 FIRE/SMOKE detected — ${alert.zone_name}`;
              } else if (violationType === "ppe_violation") {
                message = `⚠️ PPE Violation — ${alert.person_name || "Unknown"} (${(alert.confidence * 100).toFixed(0)}%)`;
              } else if (violationType === "zone_violation") {
                message = `🚨 Zone Intrusion — ${alert.person_name || "Someone"} entered ${alert.zone_name}`;
              } else if (violationType === "road_damage") {
                message = `🕳️ Road Damage detected — ${alert.zone_name}`;
              } else if (violationType === "hazard_violation") {
                message = `⚠️ Hazard Alert — ${alert.zone_name}`;
              } else {
                message = `🚨 Alert — ${alert.zone_name} (${(alert.confidence * 100).toFixed(0)}%)`;
              }

              showToast({ message, type: alert.risk_level === "high" ? "error" : "info" });

              // Audio alert
              playNotificationSound(alert.risk_level === "high");
            }
          } catch { /* pong or non-json */ }
        };

        ws.onclose = () => {
          setConnected(false);
          reconnectRef.current = setTimeout(connectWs, 3000);
        };

        ws.onerror = () => { ws.close(); };
        wsRef.current = ws;
      } catch { /* connection failed */ }
    }, 500);

    reconnectRef.current = timeout;
  }, [onAlert, onShutdown]);

  useEffect(() => {
    connectWs();
    // Load recent alerts from DB on mount
    fetch(`${API_URL}/alerts?limit=20`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data?.items) {
          const mapped: AlertData[] = data.items.map((a: any) => ({
            alert_id: a.alert_id,
            zone_name: a.zone_name,
            zone_id: a.zone_id,
            risk_level: a.risk_level,
            timestamp: a.timestamp,
            confidence: a.confidence,
            snapshot_url: a.snapshot_url,
            shutdown_triggered: a.shutdown_triggered,
            resolved: a.resolved,
            person_name: a.person_name,
            uniform_code: a.uniform_code,
          }));
          setAlerts(mapped);
        }
      })
      .catch(() => {});
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connectWs]);

  const resolveAlert = async (alertId: number) => {
    try {
      await fetch(`${API_URL}/alerts/${alertId}/resolve`, { method: "POST" });
      setAlerts((prev) => prev.map((a) => a.alert_id === alertId ? { ...a, resolved: true } : a));
      if (selectedAlert && selectedAlert.alert_id === alertId) {
        setSelectedAlert({ ...selectedAlert, resolved: true });
      }
      showToast({ message: "✅ Alert resolved", type: "success" });
      window.dispatchEvent(new Event("siews-stats-refresh"));
    } catch {}
  };

  const markFalsePositive = async (alertId: number) => {
    try {
      await fetch(`${API_URL}/alerts/${alertId}/false-positive`, { method: "POST" });
      setAlerts((prev) => prev.map((a) => a.alert_id === alertId ? { ...a, false_positive: true, resolved: true } : a));
      if (selectedAlert && selectedAlert.alert_id === alertId) {
        setSelectedAlert({ ...selectedAlert, resolved: true, false_positive: true });
      }
      showToast({ message: "🚫 Marked as false positive", type: "info" });
      window.dispatchEvent(new Event("siews-stats-refresh"));
    } catch {}
  };

  const unresolvedCount = alerts.filter((a) => !a.resolved).length;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Status bar */}
      <div className="px-3 py-2 border-b border-white/5 shrink-0">
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-gray-400 font-medium">Real-time Feed</span>
          <div className="flex items-center gap-2">
            {unresolvedCount > 0 && (
              <span className="text-[9px] font-bold text-white bg-red-500 px-1.5 py-0.5 rounded min-w-[16px] text-center">
                {unresolvedCount}
              </span>
            )}
            <div className={`status-dot ${connected ? "online" : "offline"}`} />
          </div>
        </div>
      </div>

      {/* Reconnecting banner */}
      {!connected && (
        <div className="mx-2 mt-2 px-3 py-2 rounded-lg bg-red-500/8 border border-red-500/15 flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
          <span className="text-[10px] text-red-400 font-medium">Reconnecting...</span>
        </div>
      )}

      {/* Alert List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {alerts.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-[11px] text-gray-600 font-medium">No alerts yet</p>
            <p className="text-[10px] text-gray-700 mt-1">Monitoring active...</p>
          </div>
        ) : (
          alerts.map((alert, idx) => (
            <AlertCard
              key={`${alert.alert_id || idx}-${idx}`}
              alert={alert}
              onResolve={resolveAlert}
              onFalsePositive={markFalsePositive}
              onShowDetail={(a) => setSelectedAlert(a)}
            />
          ))
        )}
      </div>

      {/* Alert Detail Overlay */}
      <DetailPanel
        isOpen={!!selectedAlert}
        onClose={() => setSelectedAlert(null)}
        title="Alert Detail"
        width="520px"
      >
        {selectedAlert && (
          <div>
            {/* Snapshot image - large */}
            {selectedAlert.snapshot_url && (
              <div className="mb-4 rounded-xl overflow-hidden border" style={{ borderColor: "var(--border)" }}>
                <img
                  src={`${API_URL}${selectedAlert.snapshot_url}`}
                  alt={`Snapshot - ${selectedAlert.zone_name}`}
                  className="w-full max-h-[300px] object-contain bg-black"
                />
              </div>
            )}

            {/* Info grid */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div className="p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
                <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Zone</p>
                <p className="text-sm font-semibold" style={{ color: "var(--text-main)" }}>{selectedAlert.zone_name}</p>
              </div>
              <div className="p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
                <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Risk Level</p>
                <span className={selectedAlert.risk_level === "high" ? "badge-high" : "badge-low"}>
                  {selectedAlert.risk_level}
                </span>
              </div>
              <div className="p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
                <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Alert Reason</p>
                <p className="text-sm font-semibold text-red-400">
                  {selectedAlert.violation_type === "ppe_violation" ? "No PPE (Helmet/Vest/Belt)" :
                   selectedAlert.violation_type === "zone_violation" ? "Restricted Zone Intrusion" :
                   selectedAlert.violation_type === "hazard_violation" ? "Environmental Hazard Detected" :
                   selectedAlert.violation_type === "fire_smoke" ? "Fire/Smoke Detected" :
                   selectedAlert.violation_type === "road_damage" ? "Road Damage Detected" :
                   selectedAlert.violation_type ? selectedAlert.violation_type.replace(/_/g, " ").toUpperCase() :
                   "Violation Detected"}
                </p>
              </div>
              <div className="p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
                <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Confidence</p>
                <p className="text-sm font-semibold font-mono" style={{ color: "var(--text-main)" }}>
                  {(selectedAlert.confidence * 100).toFixed(1)}%
                </p>
              </div>
              <div className="p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
                <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Timestamp</p>
                <p className="text-xs" style={{ color: "var(--text-main)" }}>
                  {new Date(selectedAlert.timestamp).toLocaleString()}
                </p>
              </div>
            </div>

            {/* Person name */}
            {selectedAlert.person_name && selectedAlert.person_name !== "Unknown" && (
              <div className="p-3 rounded-lg mb-4" style={{ background: "var(--bg-input)" }}>
                <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Identified Person</p>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-cyan-400">{selectedAlert.person_name}</span>
                  {selectedAlert.uniform_code && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/15 text-cyan-400">
                      {selectedAlert.uniform_code}
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Shutdown indicator */}
            {selectedAlert.shutdown_triggered && (
              <div className="p-3 rounded-lg mb-4 border border-red-500/20" style={{ background: "rgba(239,68,68,0.05)" }}>
                <p className="text-xs font-semibold text-red-400">⚠ Emergency Shutdown Triggered</p>
              </div>
            )}

            {/* Actions */}
            {!selectedAlert.resolved ? (
              <div className="flex gap-3">
                <button
                  onClick={() => resolveAlert(selectedAlert.alert_id)}
                  className="flex-1 py-2.5 rounded-lg text-sm font-medium text-white transition-all"
                  style={{ background: "var(--accent)" }}
                >
                  Resolve
                </button>
                <button
                  onClick={() => markFalsePositive(selectedAlert.alert_id)}
                  className="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all border"
                  style={{ background: "var(--bg-input)", borderColor: "var(--border)", color: "var(--text-muted)" }}
                >
                  False Positive
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-center gap-2 py-2.5 rounded-lg" style={{ background: "var(--bg-input)" }}>
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="text-sm font-medium text-emerald-500">Resolved</span>
              </div>
            )}
          </div>
        )}
      </DetailPanel>
    </div>
  );
}
