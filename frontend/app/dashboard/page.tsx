"use client";

import { useEffect, useState, useCallback } from "react";
import LoadingScreen from "@/components/LoadingScreen";
import VideoCanvas from "@/components/VideoCanvas";
import ZoneEditor from "@/components/ZoneEditor";
import AlertFeed from "@/components/AlertFeed";
import ShutdownBanner from "@/components/ShutdownBanner";
import ImageTester from "@/components/ImageTester";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface ZoneData {
  id: number;
  name: string;
  vertices: number[][];
  color: string;
  active: boolean;
  risk_level: string;
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
  person_name?: string;
  uniform_code?: string;
}

interface Stats {
  active_zones: number;
  today_alerts: number;
  unresolved_alerts: number;
  total_shutdowns: number;
  camera_status: string;
}

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [zones, setZones] = useState<ZoneData[]>([]);
  const [drawingMode, setDrawingMode] = useState(false);
  const [alertFlash, setAlertFlash] = useState(false);
  const [shutdownAlert, setShutdownAlert] = useState<AlertData | null>(null);
  const [stats, setStats] = useState<Stats>({
    active_zones: 0,
    today_alerts: 0,
    unresolved_alerts: 0,
    total_shutdowns: 0,
    camera_status: "offline",
  });
  const [showZoneDialog, setShowZoneDialog] = useState(false);
  const [pendingVertices, setPendingVertices] = useState<number[][] | null>(null);
  const [newZoneName, setNewZoneName] = useState("");
  const [newZoneRisk, setNewZoneRisk] = useState("high");
  const [facilityName, setFacilityName] = useState("Offshore Platform A");
  const [audioEnabled, setAudioEnabled] = useState(true);

  // Audio elements
  const [audioContext] = useState<AudioContext | null>(typeof window !== "undefined" ? new (window.AudioContext || (window as any).webkitAudioContext)() : null);

  const playAlertSound = useCallback((type: "entry" | "warning" | "critical" | "shutdown" | "face" | "ocr") => {
    if (!audioEnabled) return;
    
    // Using pre-generated WAVs from backend
    const soundUrls: Record<string, string> = {
      entry: `${API_URL}/static/audio/zone_entry.wav`,
      warning: `${API_URL}/static/audio/zone_warning.wav`,
      critical: `${API_URL}/static/audio/zone_critical.wav`,
      shutdown: `${API_URL}/static/audio/shutdown.wav`,
      face: `${API_URL}/static/audio/face_recognized.wav`,
      ocr: `${API_URL}/static/audio/ocr_detected.wav`,
    };

    const audio = new Audio(soundUrls[type]);
    audio.play().catch(e => console.warn("Audio play failed:", e));
  }, [audioEnabled]);

  const fetchZones = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/polygons`);
      if (res.ok) setZones(await res.json());
    } catch { /* offline */ }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/stats`);
      if (res.ok) setStats(await res.json());
    } catch { /* offline */ }
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/settings`);
      if (res.ok) {
        const s = await res.json();
        if (s.facility_name) setFacilityName(s.facility_name);
      }
    } catch { /* offline */ }
  }, []);

  useEffect(() => {
    const init = async () => {
      await Promise.all([fetchZones(), fetchStats(), fetchSettings()]);
      setTimeout(() => setLoading(false), 1200);
    };
    init();
    const interval = setInterval(fetchStats, 15000);
    return () => clearInterval(interval);
  }, [fetchZones, fetchStats, fetchSettings]);

  const handleZoneCreated = (vertices: number[][]) => {
    setPendingVertices(vertices);
    setDrawingMode(false);
    setShowZoneDialog(true);
  };

  const handleSaveZone = async () => {
    if (!pendingVertices || !newZoneName.trim()) return;
    try {
      const colors: Record<string, string> = { high: "#EF4444", low: "#F59E0B" };
      await fetch(`${API_URL}/polygons`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newZoneName,
          vertices: pendingVertices,
          color: colors[newZoneRisk] || "#EF4444",
          active: true,
          risk_level: newZoneRisk,
        }),
      });
      setShowZoneDialog(false);
      setNewZoneName("");
      setNewZoneRisk("high");
      setPendingVertices(null);
      fetchZones();
      fetchStats();
    } catch (err) {
      console.error("Failed to save zone", err);
    }
  };

  const handleAlert = useCallback((alert: AlertData) => {
    setAlertFlash(true);
    setTimeout(() => setAlertFlash(false), 2000);
    
    if (alert.person_name && alert.person_name !== "Unknown") {
      playAlertSound("face");
    } else if (alert.uniform_code) {
      playAlertSound("ocr");
    }

    if (alert.risk_level === "high") {
      setTimeout(() => playAlertSound("critical"), 500);
    } else {
      setTimeout(() => playAlertSound("warning"), 500);
    }
    
    fetchStats();
  }, [fetchStats, playAlertSound]);

  const handleShutdown = useCallback((alert: AlertData) => {
    setShutdownAlert(alert);
    playAlertSound("shutdown");
  }, [playAlertSound]);

  if (loading) return <LoadingScreen message="SYST_INIT: LOADING CORE ENGINE" />;

  return (
    <div className="min-h-screen p-5 max-w-[1920px] mx-auto">
      {/* ─── Command Bar ─── */}
      <div className="mb-4 flex items-center gap-2 flex-wrap">
        {/* Facility Label */}
        <div className="flex items-center gap-2.5 px-4 py-2 rounded-lg bg-[#0c1220]/80 border border-[#162033]">
          <svg className="w-3.5 h-3.5 text-amber-400" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm10 12h-2v-2h2v2zm0-4h-2v-2h2v2zm0-4h-2V9h2v2zm4 8h-2v-2h2v2zm0-4h-2v-2h2v2z"/>
          </svg>
          <span className="text-[11px] font-bold text-white uppercase tracking-wider">{facilityName}</span>
        </div>

        {/* Camera Status */}
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-[#0c1220]/80 border border-[#162033]">
          <span className={`status-dot ${stats.camera_status === "online" ? "online" : "offline"}`} />
          <span className="text-[10px] text-industrial-400 font-semibold uppercase tracking-wider">
            CAM: <span className={stats.camera_status === "online" ? "text-emerald-400" : "text-red-400"}>{stats.camera_status}</span>
          </span>
        </div>

        {/* Stats Chips */}
        <div className="px-3 py-2 rounded-lg bg-[#0c1220]/80 border border-[#162033] flex items-center gap-2">
          <span className="text-[10px] text-industrial-500 font-semibold uppercase tracking-wider">Zona:</span>
          <span className="text-[11px] font-bold text-amber-400 font-mono">{stats.active_zones}</span>
        </div>
        <div className="px-3 py-2 rounded-lg bg-[#0c1220]/80 border border-[#162033] flex items-center gap-2">
          <span className="text-[10px] text-industrial-500 font-semibold uppercase tracking-wider">Alert:</span>
          <span className={`text-[11px] font-bold font-mono ${stats.today_alerts > 0 ? "text-red-400" : "text-industrial-500"}`}>{stats.today_alerts}</span>
        </div>

        {/* Right-side controls */}
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setAudioEnabled(!audioEnabled)}
            className={`px-3 py-2 rounded-lg flex items-center gap-2 border transition-all duration-200 ${
              audioEnabled
                ? "bg-[#0c1220]/80 border-[#162033] text-amber-400 hover:border-amber-500/30"
                : "bg-[#0c1220]/40 border-[#162033]/50 text-industrial-600"
            }`}
          >
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
              {audioEnabled ? (
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
              ) : (
                <path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/>
              )}
            </svg>
            <span className="text-[10px] font-semibold uppercase tracking-widest">{audioEnabled ? "Audio" : "Muted"}</span>
          </button>

          {stats.camera_status === "online" && (
            <button
              onClick={async () => {
                await fetch(`${API_URL}/stream/reset`, { method: "POST" });
                window.location.reload();
              }}
              className="px-3 py-2 rounded-lg flex items-center gap-2 border bg-[#0c1220]/80 border-[#162033] text-emerald-400 hover:border-emerald-500/30 transition-all duration-200"
            >
              <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg>
              <span className="text-[10px] font-semibold uppercase tracking-widest">Reset</span>
            </button>
          )}
        </div>
      </div>

      {/* Shutdown Banner */}
      {shutdownAlert && (
        <div className="mb-4">
          <ShutdownBanner
            alert={shutdownAlert}
            onDismiss={() => {
              setShutdownAlert(null);
              fetchStats();
            }}
          />
        </div>
      )}

      {/* ─── Three Column Layout ─── */}
      <div className="flex gap-4 h-[calc(100vh-150px)] flex-col lg:flex-row items-stretch overflow-hidden">
        {/* Left Panel — Zone Control & Lab */}
        <div className="w-full lg:w-[20%] min-w-[280px] flex flex-col h-full rounded-xl bg-[#0c1220]/80 border border-[#162033] overflow-y-auto panel-glow-amber">
          <ZoneEditor
            zones={zones}
            onRefresh={fetchZones}
            onStartDrawing={() => setDrawingMode(true)}
            drawingMode={drawingMode}
          />
          <ImageTester />
        </div>

        {/* Center — Live Feed */}
        <div className="flex-1 lg:w-[55%] flex flex-col h-full overflow-hidden relative rounded-xl border border-[#162033] bg-[#050810]">
          <VideoCanvas
            zones={zones}
            drawingMode={drawingMode}
            onZoneCreated={handleZoneCreated}
            alertFlash={alertFlash}
          />
        </div>

        {/* Right Panel — Alerts */}
        <div className="w-full lg:w-[25%] min-w-[320px] flex flex-col h-full rounded-xl bg-[#0c1220]/80 border border-[#162033] overflow-hidden panel-glow-red">
          <AlertFeed onAlert={handleAlert} onShutdown={handleShutdown} />
        </div>
      </div>

      {/* ─── Zone Dialog ─── */}
      {showZoneDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-[#0c1220] border border-[#1c2a42] p-8 w-full max-w-sm animate-fade-in rounded-2xl shadow-2xl shadow-black/50">
            <h3 className="text-sm font-bold text-white mb-6 uppercase tracking-[0.2em] flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                <svg className="w-4 h-4 text-amber-400" fill="currentColor" viewBox="0 0 24 24"><path d="M3 5v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2H5c-1.11 0-2 .9-2 2zm12 4c0 1.66-1.34 3-3 3s-3-1.34-3-3 1.34-3 3-3 3 1.34 3 3zm-9 8c0-2 4-3.1 6-3.1s6 1.1 6 3.1v1H6v-1z"/></svg>
              </div>
              Zone Config
            </h3>

            <div className="space-y-5">
              <div>
                <label className="block text-[10px] font-semibold text-industrial-400 uppercase tracking-widest mb-2">Zone Name</label>
                <input
                  type="text"
                  value={newZoneName}
                  onChange={(e) => setNewZoneName(e.target.value)}
                  placeholder="WELLHEAD-ALPHA"
                  className="input-field font-mono text-xs"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-[10px] font-semibold text-industrial-400 uppercase tracking-widest mb-2">Risk Level</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setNewZoneRisk("high")}
                    className={`py-3 rounded-lg text-[11px] font-bold tracking-wider uppercase transition-all border ${
                      newZoneRisk === "high"
                        ? "bg-red-500/15 border-red-500/40 text-red-400 shadow-lg shadow-red-500/10"
                        : "bg-[#070d18] border-[#1c2a42] text-industrial-500 hover:border-[#243b5c]"
                    }`}
                  >
                    High Risk
                  </button>
                  <button
                    onClick={() => setNewZoneRisk("low")}
                    className={`py-3 rounded-lg text-[11px] font-bold tracking-wider uppercase transition-all border ${
                      newZoneRisk === "low"
                        ? "bg-amber-500/15 border-amber-500/40 text-amber-400 shadow-lg shadow-amber-500/10"
                        : "bg-[#070d18] border-[#1c2a42] text-industrial-500 hover:border-[#243b5c]"
                    }`}
                  >
                    Low Risk
                  </button>
                </div>
              </div>

              <div className="flex gap-2 pt-2">
                <button
                  onClick={() => {
                    setShowZoneDialog(false);
                    setPendingVertices(null);
                  }}
                  className="btn-ghost flex-1 text-[11px] uppercase"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveZone}
                  disabled={!newZoneName.trim()}
                  className="btn-primary flex-1 text-[11px] uppercase disabled:opacity-20"
                >
                  Confirm Area
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
