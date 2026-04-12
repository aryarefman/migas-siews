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
}

interface AlertCardProps {
  alert: AlertData;
  onResolve: (id: number) => void;
}

export default function AlertCard({ alert, onResolve }: AlertCardProps) {
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Format timestamp to WIB
  const formatTime = (ts: string) => {
    const date = new Date(ts);
    // Add 7 hours for WIB
    const wib = new Date(date.getTime() + 7 * 60 * 60 * 1000);
    const now = new Date();
    const diff = now.getTime() - date.getTime();

    if (diff < 60000) return "Baru saja";
    if (diff < 3600000) return `${Math.floor(diff / 60000)} menit lalu`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} jam lalu`;

    return wib.toLocaleString("id-ID", {
      hour: "2-digit",
      minute: "2-digit",
      day: "2-digit",
      month: "short",
    });
  };

  const isHigh = alert.risk_level === "high";

  return (
    <div
      className={`animate-slide-in p-3 border transition-all duration-200 ${
        alert.resolved
          ? "bg-industrial-950 border-industrial-900 opacity-40"
          : isHigh
          ? "bg-red-950/20 border-red-800"
          : "bg-amber-950/10 border-amber-800/40"
      }`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className={isHigh ? "badge-high" : "badge-low"}>
            {isHigh ? "HIGH" : "LOW"}
          </span>
          <span className="text-[10px] font-bold text-industrial-500 uppercase">{formatTime(alert.timestamp)}</span>
        </div>
      </div>

      {/* Zone name */}
      <p className="text-sm font-semibold text-white mb-1">{alert.zone_name}</p>

      {/* Confidence */}
      <div className="flex items-center gap-2 mb-3">
        <div className="flex-1 h-1 bg-industrial-900 overflow-hidden">
          <div
            className={`h-full transition-all ${
              isHigh ? "bg-red-600" : "bg-amber-500"
            }`}
            style={{ width: `${alert.confidence * 100}%` }}
          />
        </div>
        <span className="text-[10px] font-black font-mono text-white">
          {(alert.confidence * 100).toFixed(0)}%
        </span>
      </div>

      {/* Snapshot thumbnail */}
      {alert.snapshot_url && (
        <div className="mb-3 border border-industrial-800">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`${API_URL}${alert.snapshot_url}`}
            alt={`Snapshot - ${alert.zone_name}`}
            className="w-full h-24 object-cover grayscale opacity-80 hover:grayscale-0 hover:opacity-100 transition-all border-none"
            loading="lazy"
          />
        </div>
      )}

      {/* Resolve button */}
      {!alert.resolved && (
        <button
          onClick={() => onResolve(alert.alert_id)}
          className="w-full py-1.5 text-[10px] font-black uppercase tracking-widest bg-industrial-800 text-industrial-400 hover:bg-emerald-600 hover:text-white transition-all"
        >
          Resolve Alert
        </button>
      )}
    </div>
  );
}
