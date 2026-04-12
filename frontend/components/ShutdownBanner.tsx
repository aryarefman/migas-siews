"use client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
    return wib.toLocaleTimeString("id-ID", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  };

  const handleConfirm = async () => {
    try {
      await fetch(`${API_URL}/alerts/${alert.alert_id}/resolve`, {
        method: "POST",
      });
      onDismiss();
    } catch (err) {
      console.error("Failed to resolve", err);
    }
  };

  return (
    <div className="w-full shutdown-pulse border-2 border-red-600 bg-red-950 p-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-white flex items-center justify-center">
            <svg className="w-6 h-6 text-red-600" fill="currentColor" viewBox="0 0 24 24">
              <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/>
            </svg>
          </div>
          <div>
            <p className="text-[11px] font-black text-white tracking-[0.3em] uppercase">
              EMERGENCY SHUTDOWN ACTIVE
            </p>
            <p className="text-[10px] text-red-300 font-bold uppercase mt-1 tracking-widest">
              LOCATION: {alert.zone_name} — SECURED AT {formatTime(alert.timestamp)}
            </p>
          </div>
        </div>
        <button
          onClick={handleConfirm}
          className="px-6 py-2 bg-white text-red-600 font-black text-xs uppercase tracking-widest hover:bg-industrial-100 transition-all active:scale-95"
        >
          Konfirmasi & Reset
        </button>
      </div>
    </div>
  );
}
