"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ZoneData {
  id: number;
  name: string;
  vertices: number[][];
  color: string;
  active: boolean;
  risk_level: string;
}

interface ZoneEditorProps {
  zones: ZoneData[];
  onRefresh: () => void;
  onStartDrawing: () => void;
  drawingMode: boolean;
}

export default function ZoneEditor({
  zones,
  onRefresh,
  onStartDrawing,
  drawingMode,
}: ZoneEditorProps) {
  const [loading, setLoading] = useState<number | null>(null);

  const toggleZone = async (zone: ZoneData) => {
    setLoading(zone.id);
    try {
      await fetch(`${API_URL}/polygons/${zone.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: !zone.active }),
      });
      onRefresh();
    } catch (err) {
      console.error("Failed to toggle zone", err);
    } finally {
      setLoading(null);
    }
  };

  const deleteZone = async (zone: ZoneData) => {
    if (!confirm(`Hapus zona "${zone.name}"?`)) return;
    setLoading(zone.id);
    try {
      await fetch(`${API_URL}/polygons/${zone.id}`, { method: "DELETE" });
      onRefresh();
    } catch (err) {
      console.error("Failed to delete zone", err);
    } finally {
      setLoading(null);
    }
  };

  const activeCount = zones.filter((z) => z.active).length;

  return (
    <div className="glass-card h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-industrial-800">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-[10px] font-black text-white tracking-[0.2em] uppercase flex items-center gap-2">
            <svg className="w-3 h-3 text-amber-500" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/>
            </svg>
            Area Pantau
          </h2>
          <span className="text-[10px] text-industrial-500 font-bold bg-industrial-950 px-1.5 py-0.5 border border-industrial-800">
            {activeCount} AKTIF
          </span>
        </div>
        <button
          onClick={onStartDrawing}
          disabled={drawingMode}
          className={`w-full px-3 py-2 text-[11px] font-black uppercase tracking-widest transition-all ${
            drawingMode
              ? "bg-cyan-900/40 text-cyan-400 border border-cyan-800 cursor-not-allowed"
              : "bg-amber-500 text-industrial-950 hover:bg-amber-400 active:scale-[0.98]"
          }`}
        >
          {drawingMode ? "Drawing..." : "+ Tambah Zona"}
        </button>
      </div>

      {/* Zone List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {zones.length === 0 ? (
          <div className="text-center py-12 text-industrial-600">
            <svg className="w-8 h-8 mx-auto mb-3 opacity-20" fill="currentColor" viewBox="0 0 24 24">
              <path d="M3 5v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2H5c-1.11 0-2 .9-2 2zm12 4c0 1.66-1.34 3-3 3s-3-1.34-3-3 1.34-3 3-3 3 1.34 3 3zm-9 8c0-2 4-3.1 6-3.1s6 1.1 6 3.1v1H6v-1z"/>
            </svg>
            <p className="text-[10px] font-black uppercase tracking-widest">Zone Empty</p>
          </div>
        ) : (
          zones.map((zone) => (
            <div
              key={zone.id}
              className={`relative p-3 rounded-lg border transition-all duration-200 ${
                zone.active
                  ? "bg-industrial-800/50 border-industrial-700/50 hover:border-industrial-600/50"
                  : "bg-industrial-900/30 border-industrial-800/30 opacity-60"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  {/* Color indicator */}
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0 ring-2 ring-offset-1 ring-offset-industrial-900"
                    style={{
                      backgroundColor: zone.color,
                    }}
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-white truncate">
                      {zone.name}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span
                        className={
                          zone.risk_level === "high"
                            ? "badge-high"
                            : "badge-low"
                        }
                      >
                        {zone.risk_level === "high" ? "HIGH RISK" : "LOW RISK"}
                      </span>
                      <span className="text-[10px] text-industrial-500">
                        {zone.vertices.length} vertices
                      </span>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 flex-shrink-0">
                  {/* Toggle */}
                  <button
                    onClick={() => toggleZone(zone)}
                    disabled={loading === zone.id}
                    className="relative w-10 h-5 rounded-full transition-colors duration-200 focus:outline-none"
                    style={{
                      backgroundColor: zone.active
                        ? "rgba(16, 185, 129, 0.4)"
                        : "rgba(100, 116, 139, 0.3)",
                    }}
                    title={zone.active ? "Nonaktifkan" : "Aktifkan"}
                  >
                    <div
                      className={`absolute top-0.5 w-4 h-4 rounded-full transition-all duration-200 ${
                        zone.active
                          ? "left-5.5 bg-green-400 translate-x-1"
                          : "left-0.5 bg-industrial-400"
                      }`}
                      style={{
                        left: zone.active ? "22px" : "2px",
                      }}
                    />
                  </button>
                  {/* Delete */}
                  <button
                    onClick={() => deleteZone(zone)}
                    disabled={loading === zone.id}
                    className="p-1 rounded hover:bg-red-500/20 text-industrial-500 hover:text-red-400 transition-colors"
                    title="Hapus zona"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
