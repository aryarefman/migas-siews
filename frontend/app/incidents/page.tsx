"use client";

import { useEffect, useState, useCallback } from "react";
import LoadingScreen from "@/components/LoadingScreen";
import Modal from "@/components/Modal";
import DetailPanel from "@/components/DetailPanel";
import { showToast } from "@/components/Toast";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface Alert {
  alert_id: number;
  zone_name: string;
  risk_level: string;
  confidence: number;
  timestamp: string;
  snapshot_url: string | null;
  resolved: boolean;
  false_positive?: boolean;
  shutdown_triggered: boolean;
  person_name?: string;
  uniform_code?: string;
  violation_type?: string;
  ppe_detail?: { helmet?: boolean; vest?: boolean; belt?: boolean };
}

export default function IncidentsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/alerts?limit=100`);
      if (res.ok) {
        const data = await res.json();
        setAlerts(Array.isArray(data.items) ? data.items : []);
      }
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  const handleResolve = async (id: number) => {
    try {
      const res = await fetch(`${API_URL}/alerts/${id}/resolve`, { method: "POST" });
      if (res.ok) {
        setAlerts((prev) => prev.map((a) => (a.alert_id === id ? { ...a, resolved: true } : a)));
        if (selectedAlert && selectedAlert.alert_id === id) {
          setSelectedAlert({ ...selectedAlert, resolved: true });
        }
        window.dispatchEvent(new Event("siews-stats-refresh"));
      }
    } catch (err) { console.error(err); }
  };

  const handleFalsePositive = async (id: number) => {
    try {
      const res = await fetch(`${API_URL}/alerts/${id}/false-positive`, { method: "POST" });
      if (res.ok) {
        setAlerts((prev) => prev.map((a) => (a.alert_id === id ? { ...a, resolved: true, false_positive: true } : a)));
        if (selectedAlert && selectedAlert.alert_id === id) {
          setSelectedAlert({ ...selectedAlert, resolved: true, false_positive: true });
        }
        showToast("Marked as false positive", "success");
        window.dispatchEvent(new Event("siews-stats-refresh"));
      }
    } catch (err) { console.error(err); }
  };

  const handleResolveAll = async () => {
    try {
      const res = await fetch(`${API_URL}/alerts/resolve-all`, { method: "POST" });
      if (res.ok) {
        setAlerts((prev) => prev.map((a) => ({ ...a, resolved: true })));
        showToast("All alerts resolved", "success");
        window.dispatchEvent(new Event("siews-stats-refresh"));
      } else {
        showToast("Failed to resolve all", "error");
      }
    } catch (err) {
      console.error(err);
      showToast("Request failed", "error");
    }
    setModalOpen(false);
  };

  const filteredAlerts = (alerts || []).filter((a) => {
    if (filter === "resolved") return a.resolved;
    if (filter === "unresolved") return !a.resolved;
    if (filter === "high") return a.risk_level === "high";
    if (dateStart) {
      const d = new Date(a.timestamp);
      const start = new Date(dateStart);
      start.setHours(0, 0, 0, 0);
      if (d < start) return false;
    }
    if (dateEnd) {
      const d = new Date(a.timestamp);
      const end = new Date(dateEnd);
      end.setHours(23, 59, 59, 999);
      if (d > end) return false;
    }
    return true;
  });

  const unresolvedCount = alerts.filter(a => !a.resolved).length;

  const exportCSV = () => {
    const csvData = [
      ["ID", "Zone", "Risk", "Confidence", "Timestamp", "Resolved", "False Positive", "Violation Type", "Person Name", "Uniform Code", "PPE Detail", "Shutdown"],
      ...filteredAlerts.map(a => [
        a.alert_id,
        `"${a.zone_name}"`,
        a.risk_level,
        (a.confidence * 100).toFixed(0) + "%",
        a.timestamp,
        a.resolved ? "Yes" : "No",
        a.false_positive ? "Yes" : "No",
        a.violation_type || "",
        a.person_name || "",
        a.uniform_code || "",
        a.ppe_detail ? JSON.stringify(a.ppe_detail) : "",
        a.shutdown_triggered ? "Yes" : "No",
      ])
    ].map(e => e.join(",")).join("\n");
    const blob = new Blob([csvData], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `siews-incidents-${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
  };

  if (loading) return <LoadingScreen message="Loading incidents..." />;

  return (
    <div className="min-h-screen p-5 max-w-6xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl font-bold text-[var(--text-main)] tracking-tight">Incidents</h1>
          <p className="text-sm text-[var(--text-muted)] mt-1">Safety violations and alert history</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => unresolvedCount > 0 && setModalOpen(true)}
            disabled={unresolvedCount === 0}
            className="btn-danger text-xs disabled:opacity-40"
          >
            Resolve All ({unresolvedCount})
          </button>
          <button
            onClick={async () => {
              if (!confirm("Delete ALL alerts and snapshots? This cannot be undone.")) return;
              try {
                const res = await fetch(`${API_URL}/alerts`, { method: "DELETE" });
                if (res.ok) {
                  setAlerts([]);
                  showToast({ message: "All alerts deleted", type: "success" });
                  window.dispatchEvent(new Event("siews-stats-refresh"));
                }
              } catch { showToast({ message: "Delete failed", type: "error" }); }
            }}
            disabled={alerts.length === 0}
            className="btn-danger text-xs disabled:opacity-40"
          >
            Delete All
          </button>
          <button onClick={exportCSV} className="btn-ghost text-xs">Export CSV</button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 mb-6 overflow-x-auto pb-2">
        {["all", "unresolved", "resolved", "high"].map((f) => (
          <button
            key={f} onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-lg text-xs font-medium border transition-all ${
              filter === f
                ? "bg-[var(--accent)]/10 border-[var(--accent)]/30 text-[var(--accent-light)]"
                : "bg-[var(--bg-surface)] border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-main)] hover:border-[var(--border-bright)]"
            }`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
        <span className="text-xs text-[var(--text-faint)] ml-2">{filteredAlerts.length} results</span>
      </div>

      {/* Date range filter */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xs text-[var(--text-muted)]">From:</span>
        <input
          type="date"
          value={dateStart}
          onChange={e => setDateStart(e.target.value)}
          className="input-field text-xs py-1.5"
        />
        <span className="text-xs text-[var(--text-muted)]">To:</span>
        <input
          type="date"
          value={dateEnd}
          onChange={e => setDateEnd(e.target.value)}
          className="input-field text-xs py-1.5"
        />
        {(dateStart || dateEnd) && (
          <button onClick={() => { setDateStart(""); setDateEnd(""); }} className="text-xs text-[var(--accent)] hover:underline">
            Clear
          </button>
        )}
      </div>

      {/* Table */}
      <div className="surface-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-[var(--border)]">
                <th className="px-5 py-3.5 text-[11px] font-semibold text-[var(--text-faint)] uppercase tracking-wider">Zone</th>
                <th className="px-5 py-3.5 text-[11px] font-semibold text-[var(--text-faint)] uppercase tracking-wider">Risk</th>
                <th className="px-5 py-3.5 text-[11px] font-semibold text-[var(--text-faint)] uppercase tracking-wider">Confidence</th>
                <th className="px-5 py-3.5 text-[11px] font-semibold text-[var(--text-faint)] uppercase tracking-wider">Time</th>
                <th className="px-5 py-3.5 text-[11px] font-semibold text-[var(--text-faint)] uppercase tracking-wider">Status</th>
                <th className="px-5 py-3.5 text-[11px] font-semibold text-[var(--text-faint)] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {filteredAlerts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-16 text-center">
                    <p className="text-sm text-[var(--text-faint)]">No incidents found</p>
                  </td>
                </tr>
              ) : (
                filteredAlerts.map((alert) => (
                  <tr
                    key={alert.alert_id}
                    className="hover:bg-[var(--bg-input)] transition-colors cursor-pointer"
                    onClick={() => setSelectedAlert(alert)}
                  >
                    <td className="px-5 py-4">
                      <div>
                        <p className="text-sm font-medium text-[var(--text-main)]">{alert.zone_name}</p>
                        <p className="text-[10px] text-[var(--text-faint)] font-mono">#{alert.alert_id}</p>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <span className={alert.risk_level === "high" ? "badge-high" : "badge-low"}>{alert.risk_level}</span>
                    </td>
                    <td className="px-5 py-4">
                      <span className="text-xs font-mono text-[var(--text-muted)]">{(alert.confidence * 100).toFixed(0)}%</span>
                    </td>
                    <td className="px-5 py-4">
                      <span className="text-xs text-[var(--text-muted)]">{new Date(alert.timestamp).toLocaleString()}</span>
                    </td>
                    <td className="px-5 py-4">
                      {alert.resolved ? (
                        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-emerald-500">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                          Resolved
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-red-400">
                          <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
                          Active
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-1.5">
                        {!alert.resolved && (
                          <>
                            <button onClick={(e) => { e.stopPropagation(); handleResolve(alert.alert_id); }} className="btn-ghost text-[10px] py-1 px-2">Resolve</button>
                            <button onClick={(e) => { e.stopPropagation(); handleFalsePositive(alert.alert_id); }} className="btn-ghost text-[10px] py-1 px-2">False +</button>
                          </>
                        )}
                        {alert.resolved && alert.snapshot_url && (
                          <button onClick={(e) => { e.stopPropagation(); setSelectedAlert(alert); }} className="btn-ghost text-[10px] py-1 px-2">View</button>
                        )}
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            try {
                              await fetch(`${API_URL}/alerts/${alert.alert_id}`, { method: "DELETE" });
                              setAlerts((prev) => prev.filter((a) => a.alert_id !== alert.alert_id));
                              window.dispatchEvent(new Event("siews-stats-refresh"));
                            } catch {}
                          }}
                          className="p-1 rounded hover:bg-red-500/10 text-[var(--text-faint)] hover:text-red-400 transition-all"
                          title="Delete alert"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Alert Detail Overlay */}
      <DetailPanel
        isOpen={!!selectedAlert}
        onClose={() => setSelectedAlert(null)}
        title="Incident Detail"
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

            {/* PPE Detail icons */}
            {selectedAlert.ppe_detail && selectedAlert.violation_type === "ppe_violation" && (
              <div className="p-3 rounded-lg mb-4" style={{ background: "var(--bg-input)" }}>
                <p className="text-[10px] font-medium mb-2" style={{ color: "var(--text-faint)" }}>PPE Status</p>
                <div className="flex gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className={`text-base ${selectedAlert.ppe_detail.helmet ? "text-emerald-400" : "text-red-400"}`}>
                      {selectedAlert.ppe_detail.helmet ? "✓" : "✗"}
                    </span>
                    <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>Helmet</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className={`text-base ${selectedAlert.ppe_detail.vest ? "text-emerald-400" : "text-red-400"}`}>
                      {selectedAlert.ppe_detail.vest ? "✓" : "✗"}
                    </span>
                    <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>Vest</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className={`text-base ${selectedAlert.ppe_detail.belt ? "text-emerald-400" : "text-red-400"}`}>
                      {selectedAlert.ppe_detail.belt ? "✓" : "✗"}
                    </span>
                    <span className="text-[11px]" style={{ color: "var(--text-muted)" }}>Belt</span>
                  </div>
                </div>
              </div>
            )}

            {/* Alert ID */}
            <div className="p-3 rounded-lg mb-4" style={{ background: "var(--bg-input)" }}>
              <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Alert ID</p>
              <p className="text-xs font-mono" style={{ color: "var(--text-main)" }}>#{selectedAlert.alert_id}</p>
            </div>

            {/* Shutdown indicator */}
            {selectedAlert.shutdown_triggered && (
              <div className="p-3 rounded-lg mb-4 border border-red-500/20" style={{ background: "rgba(239,68,68,0.05)" }}>
                <p className="text-xs font-semibold text-red-400">⚠ Emergency Shutdown Triggered</p>
              </div>
            )}

            {/* False positive badge */}
            {selectedAlert.false_positive && (
              <div className="p-3 rounded-lg mb-4 border border-dashed border-gray-500/20" style={{ background: "var(--bg-input)" }}>
                <p className="text-xs font-semibold text-gray-400 text-center">False Positive</p>
              </div>
            )}

            {/* Actions */}
            {!selectedAlert.resolved ? (
              <div className="flex gap-3">
                <button
                  onClick={() => handleResolve(selectedAlert.alert_id)}
                  className="flex-1 py-2.5 rounded-lg text-sm font-medium text-white transition-all"
                  style={{ background: "var(--accent)" }}
                >
                  Resolve
                </button>
                <button
                  onClick={() => handleFalsePositive(selectedAlert.alert_id)}
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

      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onConfirm={handleResolveAll}
        title="Resolve All Alerts"
        message={`This will resolve all ${unresolvedCount} unresolved alerts. Are you sure?`}
        confirmText="Resolve All"
        cancelText="Cancel"
        type="warning"
      />
    </div>
  );
}
