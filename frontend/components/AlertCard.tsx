"use client";

import { useState } from "react";

interface DetectionCrop {
  id: number;
  class_name: string;
  confidence: number;
  crop_url: string | null;
  frame_number: number | null;
  bbox: number[] | null;
  is_false_positive: boolean;
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
  ppe_detail?: Record<string, number>;
  false_positive?: boolean;
}

interface AlertCardProps {
  alert: AlertData;
  onResolve: (id: number) => void;
  onFalsePositive?: (id: number) => void;
}

const VIOLATION_LABELS: Record<string, { label: string; color: string }> = {
  restricted_area: { label: "ZONA TERLARANG", color: "text-red-400" },
  missing_ppe: { label: "PPE TIDAK LENGKAP", color: "text-orange-400" },
  no_harness: { label: "TANPA HARNESS", color: "text-yellow-400" },
  fire_smoke: { label: "API / ASAP", color: "text-orange-500" },
  multiple: { label: "MULTI PELANGGARAN", color: "text-red-500" },
};

export default function AlertCard({ alert, onResolve, onFalsePositive }: AlertCardProps) {
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const [showCrops, setShowCrops] = useState(false);
  const [crops, setCrops] = useState<DetectionCrop[]>([]);
  const [loadingCrops, setLoadingCrops] = useState(false);

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

  const handleShowCrops = async () => {
    setLoadingCrops(true);
    setShowCrops(true);
    try {
      const res = await fetch(`${API_URL}/alerts/${alert.alert_id}/detections`);
      if (res.ok) setCrops(await res.json());
    } catch { /* offline */ }
    finally { setLoadingCrops(false); }
  };

  const isHigh = alert.risk_level === "high";
  const viol = alert.violation_type ? VIOLATION_LABELS[alert.violation_type] : null;
  const ppeEntries = alert.ppe_detail ? Object.entries(alert.ppe_detail) : [];

  return (
    <>
      <div
        className={`animate-slide-in p-3 border transition-all duration-200 ${alert.false_positive
            ? "bg-industrial-950 border-industrial-900 opacity-30"
            : alert.resolved
              ? "bg-industrial-950 border-industrial-900 opacity-40"
              : isHigh
                ? "bg-red-950/20 border-red-800"
                : "bg-amber-950/10 border-amber-800/40"
          }`}
      >
        {/* Header row */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={isHigh ? "badge-high" : "badge-low"}>
              {isHigh ? "HIGH" : "LOW"}
            </span>
            {viol && (
              <span className={`text-[9px] font-black uppercase tracking-wider ${viol.color}`}>
                {viol.label}
              </span>
            )}
          </div>
          <span className="text-[10px] font-bold text-industrial-500 uppercase">{formatTime(alert.timestamp)}</span>
        </div>

        {/* Zone name */}
        <p className="text-sm font-semibold text-white mb-1">{alert.zone_name}</p>

        {/* PPE detail chips */}
        {ppeEntries.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-2">
            {ppeEntries.map(([cls, conf]) => (
              <span
                key={cls}
                className={`px-1.5 py-0.5 text-[9px] font-bold uppercase border ${cls.startsWith("no_")
                    ? "border-red-700 text-red-400 bg-red-950/30"
                    : "border-emerald-800 text-emerald-500 bg-emerald-950/20"
                  }`}
              >
                {cls.replace("_", " ")} {(conf * 100).toFixed(0)}%
              </span>
            ))}
          </div>
        )}

        {/* Confidence bar */}
        <div className="flex items-center gap-2 mb-3">
          <div className="flex-1 h-1 bg-industrial-900 overflow-hidden">
            <div
              className={`h-full transition-all ${isHigh ? "bg-red-600" : "bg-amber-500"}`}
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

        {/* Action buttons */}
        {!alert.resolved && !alert.false_positive && (
          <div className="grid grid-cols-3 gap-1">
            <button
              onClick={handleShowCrops}
              className="py-1.5 text-[9px] font-black uppercase tracking-wider bg-industrial-800 text-industrial-400 hover:bg-industrial-700 hover:text-white transition-all col-span-1"
            >
              Crops
            </button>
            <button
              onClick={() => onResolve(alert.alert_id)}
              className="py-1.5 text-[9px] font-black uppercase tracking-wider bg-industrial-800 text-industrial-400 hover:bg-emerald-600 hover:text-white transition-all col-span-1"
            >
              Resolve
            </button>
            <button
              onClick={() => onFalsePositive?.(alert.alert_id)}
              className="py-1.5 text-[9px] font-black uppercase tracking-wider bg-industrial-800 text-industrial-400 hover:bg-sky-700 hover:text-white transition-all col-span-1"
            >
              FP
            </button>
          </div>
        )}

        {alert.false_positive && (
          <div className="text-[9px] text-sky-500 font-bold uppercase tracking-wider text-center py-1">
            ✓ FALSE POSITIVE
          </div>
        )}
      </div>

      {/* Detection Crops Modal */}
      {showCrops && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-industrial-950/90 p-4">
          <div className="bg-industrial-900 border border-industrial-700 w-full max-w-lg max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-industrial-800">
              <h3 className="text-[11px] font-black text-white uppercase tracking-widest">
                Object Crops — Alert #{alert.alert_id}
              </h3>
              <button
                onClick={() => setShowCrops(false)}
                className="text-industrial-500 hover:text-white text-lg leading-none"
              >
                ✕
              </button>
            </div>
            <div className="overflow-y-auto p-4 flex-1">
              {loadingCrops ? (
                <p className="text-industrial-500 text-xs text-center py-8">Loading crops...</p>
              ) : crops.length === 0 ? (
                <p className="text-industrial-500 text-xs text-center py-8">No object crops available.</p>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  {crops.map((crop) => (
                    <div key={crop.id} className="border border-industrial-800 p-2">
                      {crop.crop_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={`${API_URL}${crop.crop_url}`}
                          alt={crop.class_name}
                          className="w-full h-28 object-cover mb-2"
                        />
                      ) : (
                        <div className="w-full h-28 bg-industrial-950 flex items-center justify-center mb-2">
                          <span className="text-[9px] text-industrial-600">No Image</span>
                        </div>
                      )}
                      <p className={`text-[10px] font-black uppercase ${crop.class_name.startsWith("no_") ? "text-red-400" : "text-emerald-400"
                        }`}>
                        {crop.class_name.replace("_", " ")}
                      </p>
                      <p className="text-[9px] text-industrial-500">
                        Conf: {(crop.confidence * 100).toFixed(0)}%
                        {crop.frame_number != null && ` · Frame ${crop.frame_number}`}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
