"use client";

import { useState } from "react";
import SnapshotModal from "./SnapshotModal";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

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
  false_positive?: boolean;
  person_name?: string;
  uniform_code?: string;
  violation_type?: string;
}

interface AlertCardProps {
  alert: AlertData;
  onResolve: (id: number) => void;
  onFalsePositive: (id: number) => void;
  onShowDetail?: (alert: AlertData) => void;
}

export default function AlertCard({ alert, onResolve, onFalsePositive, onShowDetail }: AlertCardProps) {
  const [showSnapshot, setShowSnapshot] = useState(false);

  const formatTime = (ts: string) => {
    const date = new Date(ts);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    if (diff < 60000) return "Just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  const isHigh = alert.risk_level === "high";

  const handleCardClick = () => {
    if (onShowDetail) {
      onShowDetail(alert);
    }
  };

  return (
    <>
      <div
        className={`animate-slide-in rounded-xl p-3 border transition-all duration-200 ${
          onShowDetail ? "cursor-pointer" : ""
        } ${
          alert.false_positive
            ? "bg-white/[0.01] border-dashed border-white/[0.12] opacity-50"
            : alert.resolved
            ? "bg-white/[0.01] border-white/[0.03] opacity-40"
            : isHigh
            ? "bg-red-500/5 border-red-500/15"
            : "bg-amber-500/5 border-amber-500/10"
        }`}
        role="article"
        aria-label={`Alert: ${alert.zone_name}, ${isHigh ? "high" : "low"} risk`}
        onClick={handleCardClick}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-1.5">
          <span className={isHigh ? "badge-high" : "badge-low"}>
            {isHigh ? "High" : "Low"}
          </span>
          <span className="text-[10px] text-gray-500 font-medium">{formatTime(alert.timestamp)}</span>
        </div>

        {/* Zone name */}
        <p className="text-[12px] font-semibold text-white mb-0.5">{alert.zone_name}</p>

        {/* Violation reason */}
        {alert.violation_type && (
          <p className="text-[10px] text-red-400 mb-1.5">
            {alert.violation_type === "ppe_violation" ? "No PPE" :
             alert.violation_type === "zone_violation" ? "Restricted Zone" :
             alert.violation_type === "hazard_violation" ? "Environmental Hazard" :
             alert.violation_type === "fire_smoke" ? "Fire/Smoke" :
             alert.violation_type === "road_damage" ? "Road Damage" :
             alert.violation_type.replace(/_/g, " ")}
          </p>
        )}

        {/* Person identification */}
        {alert.person_name && alert.person_name !== "Unknown" && (
          <div className="flex items-center gap-1.5 mb-2 flex-wrap">
            <span className="text-[10px] font-semibold text-cyan-400 bg-cyan-500/10 px-1.5 py-0.5 rounded border border-cyan-500/15">
              {alert.person_name}
            </span>
            {alert.uniform_code && (
              <span className="text-[10px] text-cyan-300/70 bg-cyan-500/5 px-1.5 py-0.5 rounded border border-cyan-500/10">
                {alert.uniform_code}
              </span>
            )}
          </div>
        )}

        {/* Confidence bar */}
        <div className="flex items-center gap-2 mb-2">
          <div className="flex-1 h-1 bg-black/30 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${isHigh ? "bg-red-500" : "bg-amber-500"}`}
              style={{ width: `${alert.confidence * 100}%` }}
            />
          </div>
          <span className="text-[10px] font-bold font-mono text-gray-300">
            {(alert.confidence * 100).toFixed(0)}%
          </span>
        </div>

        {/* Snapshot thumbnail */}
        {alert.snapshot_url && (
          <button
            onClick={(e) => { e.stopPropagation(); setShowSnapshot(true); }}
            className="mb-2 rounded-lg overflow-hidden border border-white/5 w-full block hover:border-white/10 transition-colors cursor-zoom-in"
            aria-label="Enlarge snapshot"
          >
            <img
              src={`${API_URL}${alert.snapshot_url}`}
              alt={`Snapshot - ${alert.zone_name}`}
              className="w-full h-20 object-cover opacity-75 hover:opacity-100 transition-opacity"
              loading="lazy"
            />
          </button>
        )}

        {/* Actions */}
        {!alert.resolved && (
          <div className="flex gap-1.5">
            <button
              onClick={(e) => { e.stopPropagation(); onResolve(alert.alert_id); }}
              className="flex-1 py-1.5 rounded-lg text-[10px] font-semibold bg-white/[0.03] border border-white/[0.06] text-gray-400 hover:bg-emerald-500/10 hover:border-emerald-500/20 hover:text-emerald-400 transition-all"
            >
              Resolve
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onFalsePositive(alert.alert_id); }}
              className="flex-1 py-1.5 rounded-lg text-[10px] font-semibold bg-white/[0.02] border border-white/[0.04] text-gray-500 hover:border-red-500/15 hover:text-red-400 transition-all"
            >
              False +
            </button>
          </div>
        )}
      </div>

      {/* Fullscreen Snapshot Modal */}
      {showSnapshot && alert.snapshot_url && (
        <SnapshotModal
          src={`${API_URL}${alert.snapshot_url}`}
          alt={`Snapshot - ${alert.zone_name}`}
          onClose={() => setShowSnapshot(false)}
        />
      )}
    </>
  );
}
