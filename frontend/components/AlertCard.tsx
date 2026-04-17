"use client";

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
  person_name?: string;
  uniform_code?: string;
}

interface AlertCardProps {
  alert: AlertData;
  onResolve: (id: number) => void;
  onFalsePositive: (id: number) => void;
}

export default function AlertCard({ alert, onResolve, onFalsePositive }: AlertCardProps) {
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

  const formatTime = (ts: string) => {
    const date = new Date(ts);
    const wib = new Date(date.getTime() + 7 * 60 * 60 * 1000);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    if (diff < 60000) return "Baru saja";
    if (diff < 3600000) return `${Math.floor(diff / 60000)} menit lalu`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} jam lalu`;
    return wib.toLocaleString("id-ID", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" });
  };

  const isHigh = alert.risk_level === "high";

  return (
    <div
      className={`animate-slide-in rounded-xl p-3 border transition-all duration-200 ${
        alert.resolved
          ? "bg-[#070d18]/60 border-[#162033]/40 opacity-40"
          : isHigh
          ? "bg-red-500/5 border-red-500/20"
          : "bg-amber-500/5 border-amber-500/15"
      }`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={isHigh ? "badge-high" : "badge-low"}>{isHigh ? "HIGH" : "LOW"}</span>
          <span className="text-[10px] font-semibold text-industrial-500">{formatTime(alert.timestamp)}</span>
        </div>
      </div>

      {/* Zone name */}
      <p className="text-sm font-semibold text-white mb-1">{alert.zone_name}</p>

      {/* Identification */}
      {(alert.person_name || alert.uniform_code) && (
        <div className="flex items-center gap-2 mb-2">
          {alert.person_name && alert.person_name !== "Unknown" ? (
            <div className="flex items-center gap-1.5 text-[9px] font-bold text-cyan-400 uppercase tracking-wider bg-cyan-500/8 px-2 py-0.5 rounded-md border border-cyan-500/15">
              <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08s5.97 1.09 6 3.08c-1.29 1.94-3.5 3.22-6 3.22z"/></svg>
              {alert.person_name}
            </div>
          ) : alert.uniform_code ? (
            <div className="flex items-center gap-1.5 text-[9px] font-bold text-amber-400 uppercase tracking-wider bg-amber-500/8 px-2 py-0.5 rounded-md border border-amber-500/15">
              <svg className="w-2.5 h-2.5" fill="currentColor" viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14h-4v-2h4v2zm0-4h-4v-2h4v2zm0-4h-4V7h4v2z"/></svg>
              ID: {alert.uniform_code}
            </div>
          ) : null}
        </div>
      )}

      {/* Confidence */}
      <div className="flex items-center gap-2 mb-3">
        <div className="flex-1 h-1 bg-[#070d18] rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all ${isHigh ? "bg-red-500" : "bg-amber-500"}`} style={{ width: `${alert.confidence * 100}%` }} />
        </div>
        <span className="text-[10px] font-bold font-mono text-white">{(alert.confidence * 100).toFixed(0)}%</span>
      </div>

      {/* Snapshot */}
      {alert.snapshot_url && (
        <div className="mb-3 rounded-lg overflow-hidden border border-[#162033]">
          <img src={`${API_URL}${alert.snapshot_url}`} alt={`Snapshot - ${alert.zone_name}`}
            className="w-full h-20 object-cover grayscale opacity-70 hover:grayscale-0 hover:opacity-100 transition-all duration-300" loading="lazy" />
        </div>
      )}

      {/* Actions */}
      {!alert.resolved && (
        <div className="flex gap-1.5">
          <button onClick={() => onResolve(alert.alert_id)}
            className="flex-1 py-1.5 rounded-lg text-[9px] font-bold uppercase tracking-wider bg-[#0f1729] border border-[#1c2a42] text-industrial-400 hover:bg-emerald-500/15 hover:border-emerald-500/25 hover:text-emerald-400 transition-all">
            Resolve
          </button>
          <button onClick={() => onFalsePositive(alert.alert_id)}
            className="flex-1 py-1.5 rounded-lg text-[9px] font-bold uppercase tracking-wider bg-[#070d18] border border-[#162033] text-industrial-600 hover:border-red-500/20 hover:text-red-400 transition-all">
            False Pos
          </button>
        </div>
      )}
    </div>
  );
}
