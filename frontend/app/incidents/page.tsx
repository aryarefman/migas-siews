"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import LoadingScreen from "@/components/LoadingScreen";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface Alert {
  alert_id: number;
  zone_name: string;
  risk_level: string;
  confidence: number;
  timestamp: string;
  snapshot_url: string | null;
  resolved: boolean;
  shutdown_triggered: boolean;
}

export default function IncidentsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  const fetchAlerts = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/alerts?limit=100`);
      if (res.ok) {
        const data = await res.json();
        setAlerts(Array.isArray(data.items) ? data.items : []);
      }
    } catch (err) { console.error(err); }
    finally { setTimeout(() => setLoading(false), 1000); }
  }, []);

  useEffect(() => { fetchAlerts(); }, [fetchAlerts]);

  const handleResolve = async (id: number) => {
    try {
      const res = await fetch(`${API_URL}/alerts/${id}/resolve`, { method: "POST" });
      if (res.ok) setAlerts((prev) => prev.map((a) => (a.alert_id === id ? { ...a, resolved: true } : a)));
    } catch (err) { console.error(err); }
  };

  const handleBulkResolve = async () => {
    const unresolved = alerts.filter((a) => !a.resolved);
    if (unresolved.length === 0) return;
    if (confirm(`Resolve ${unresolved.length} unresolved alerts?`)) {
      for (const alert of unresolved) await handleResolve(alert.alert_id);
    }
  };

  const filteredAlerts = (alerts || []).filter((a) => {
    if (filter === "resolved") return a.resolved;
    if (filter === "unresolved") return !a.resolved;
    if (filter === "high") return a.risk_level === "high";
    return true;
  });

  if (loading) return <LoadingScreen message="AUTH: FETCHING ARCHIVAL DATA" />;

  return (
    <div className="min-h-screen p-5 max-w-6xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <div className="w-8 h-8 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center">
              <svg className="w-4 h-4 text-red-400" fill="currentColor" viewBox="0 0 24 24">
                <path d="M13 14h-2V9h2v5zm0 4h-2v-2h2v2zm-12 3h22L12 2 1 21z"/>
              </svg>
            </div>
            <h1 className="text-xl font-extrabold text-white tracking-tight">Incident Logs</h1>
          </div>
          <p className="text-[10px] text-industrial-500 font-semibold uppercase tracking-wider ml-11">Historical safety violations and system alerts</p>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={handleBulkResolve} className="btn-ghost text-[10px] uppercase tracking-wider">Bulk Resolve</button>
          <button
            onClick={() => {
              const csvData = [
                ["ID", "Zone", "Risk", "Confidence", "Timestamp", "Resolved"],
                ...filteredAlerts.map(a => [a.alert_id, a.zone_name, a.risk_level, a.confidence, a.timestamp, a.resolved])
              ].map(e => e.join(",")).join("\n");
              const blob = new Blob([csvData], { type: 'text/csv' });
              const url = window.URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url; a.download = `siews-incidents-${new Date().toISOString().split('T')[0]}.csv`; a.click();
            }}
            className="btn-primary text-[10px] uppercase tracking-wider"
          >Export CSV</button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 mb-6 overflow-x-auto pb-2">
        {["all", "unresolved", "resolved", "high"].map((f) => (
          <button
            key={f} onClick={() => setFilter(f)}
            className={`px-4 py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider border transition-all duration-200 ${
              filter === f
                ? "bg-amber-500/15 border-amber-500/30 text-amber-400"
                : "bg-[#0c1220]/60 border-[#162033] text-industrial-500 hover:text-white hover:border-[#1c2a42]"
            }`}
          >{f}</button>
        ))}
      </div>

      {/* Table */}
      <div className="rounded-xl bg-[#0c1220]/80 border border-[#162033] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-[#162033] bg-[#070d18]">
                <th className="px-5 py-3.5 text-[10px] font-bold text-industrial-500 uppercase tracking-wider">Incident</th>
                <th className="px-5 py-3.5 text-[10px] font-bold text-industrial-500 uppercase tracking-wider">Risk</th>
                <th className="px-5 py-3.5 text-[10px] font-bold text-industrial-500 uppercase tracking-wider">Conf.</th>
                <th className="px-5 py-3.5 text-[10px] font-bold text-industrial-500 uppercase tracking-wider">Timestamp</th>
                <th className="px-5 py-3.5 text-[10px] font-bold text-industrial-500 uppercase tracking-wider">Status</th>
                <th className="px-5 py-3.5 text-[10px] font-bold text-industrial-500 uppercase tracking-wider">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#162033]/60">
              {filteredAlerts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-16 text-center text-industrial-600">
                    <p className="text-[10px] font-bold uppercase tracking-wider">No matching logs found</p>
                  </td>
                </tr>
              ) : (
                filteredAlerts.map((alert) => (
                  <tr key={alert.alert_id} className="hover:bg-[#0f1729]/50 transition-colors">
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-[#070d18] border border-[#1c2a42] flex items-center justify-center shrink-0">
                          <svg className="w-4 h-4 text-industrial-500" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/>
                          </svg>
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-white truncate">{alert.zone_name}</p>
                          <p className="text-[10px] text-industrial-500 font-mono">#{alert.alert_id}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4"><span className={alert.risk_level === "high" ? "badge-high" : "badge-low"}>{alert.risk_level}</span></td>
                    <td className="px-5 py-4"><span className="text-xs font-mono text-industrial-400">{(alert.confidence * 100).toFixed(0)}%</span></td>
                    <td className="px-5 py-4"><span className="text-xs font-mono text-industrial-500">{new Date(alert.timestamp).toLocaleString()}</span></td>
                    <td className="px-5 py-4">
                      {alert.resolved ? (
                        <span className="inline-flex items-center gap-1.5 text-[10px] font-bold text-emerald-400 uppercase tracking-wider">
                          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Resolved
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-[10px] font-bold text-red-400 uppercase tracking-wider animate-pulse">
                          <div className="w-1.5 h-1.5 rounded-full bg-red-400" /> Active
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-4">
                      {!alert.resolved ? (
                        <button onClick={() => handleResolve(alert.alert_id)} className="px-3 py-1.5 rounded-lg bg-[#0f1729] border border-[#1c2a42] text-industrial-300 text-[10px] font-bold uppercase tracking-wider hover:bg-emerald-500/15 hover:border-emerald-500/30 hover:text-emerald-400 transition-all">
                          Resolve
                        </button>
                      ) : (
                        <Link href={`${API_URL}${alert.snapshot_url}`} target="_blank" className="px-3 py-1.5 rounded-lg bg-[#070d18] border border-[#162033] text-industrial-500 text-[10px] font-bold uppercase tracking-wider hover:text-white transition-all">
                          View
                        </Link>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
