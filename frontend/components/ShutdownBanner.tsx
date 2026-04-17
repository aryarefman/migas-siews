"use client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface ShutdownBannerProps {
  alert: {
    alert_id: number;
    zone_name: string;
    timestamp: string;
    risk_level: string;
  } | null;
  onDismiss: () => void;
}

export default function ShutdownBanner({ alert, onDismiss }: ShutdownBannerProps) {
  if (!alert) return null;

  const formatTime = (ts: string) => {
    const date = new Date(ts);
    const wib = new Date(date.getTime() + 7 * 60 * 60 * 1000);
    return wib.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  const handleConfirm = async () => {
    try {
      await fetch(`${API_URL}/alerts/${alert.alert_id}/resolve`, { method: "POST" });
      onDismiss();
    } catch (err) { console.error("Failed to resolve", err); }
  };

  return (
    <div className="w-full shutdown-pulse rounded-xl border border-red-500/40 bg-red-500/8 backdrop-blur-sm p-5">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <div className="w-11 h-11 rounded-xl bg-red-500/15 border border-red-500/30 flex items-center justify-center">
            <svg className="w-6 h-6 text-red-400" fill="currentColor" viewBox="0 0 24 24">
              <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/>
            </svg>
          </div>
          <div>
            <p className="text-sm font-bold text-white tracking-wider uppercase">
              Emergency Shutdown Active
            </p>
            <p className="text-[10px] text-red-300/80 font-semibold uppercase mt-0.5 tracking-wider">
              Location: {alert.zone_name} — Secured at {formatTime(alert.timestamp)}
            </p>
          </div>
        </div>
        <button
          onClick={handleConfirm}
          className="px-5 py-2.5 rounded-lg bg-red-500 text-white font-bold text-xs uppercase tracking-wider hover:bg-red-400 transition-all active:scale-[0.97] shadow-lg shadow-red-500/25"
        >
          Confirm & Reset
        </button>
      </div>
    </div>
  );
}
