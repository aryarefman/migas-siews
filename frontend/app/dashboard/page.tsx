"use client";

import { useEffect, useState, useCallback } from "react";
import LoadingScreen from "@/components/LoadingScreen";
import VideoCanvas from "@/components/VideoCanvas";
import ZoneEditor from "@/components/ZoneEditor";
import AlertFeed from "@/components/AlertFeed";
import ShutdownBanner from "@/components/ShutdownBanner";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
      // Artificial delay for better UX feel of the high-tech loader
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

  const handleAlert = useCallback(() => {
    setAlertFlash(true);
    setTimeout(() => setAlertFlash(false), 2000);
    fetchStats();
  }, [fetchStats]);

  const handleShutdown = useCallback((alert: AlertData) => {
    setShutdownAlert(alert);
  }, []);

  if (loading) return <LoadingScreen message="SYST_INIT: LOADING CORE ENGINE" />;

  return (
    <div className="min-h-screen p-4 max-w-[1920px] mx-auto">
      {/* Status Bar */}
      <div className="mb-4 flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-2 px-3 py-1.5 bg-industrial-900 border border-industrial-800">
          <svg className="w-3.5 h-3.5 text-amber-500" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm10 12h-2v-2h2v2zm0-4h-2v-2h2v2zm0-4h-2V9h2v2zm4 8h-2v-2h2v2zm0-4h-2v-2h2v2z"/>
          </svg>
          <span className="text-[10px] font-black text-white uppercase tracking-wider">{facilityName}</span>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 bg-industrial-900 border border-industrial-800">
          <div className={`w-1.5 h-1.5 ${stats.camera_status === "online" ? "bg-emerald-500" : "bg-red-500"}`} />
          <span className="text-[10px] text-industrial-500 font-bold uppercase tracking-wider">
            CAM: <span className={stats.camera_status === "online" ? "text-emerald-400" : "text-red-400"}>{stats.camera_status}</span>
          </span>
        </div>
        <div className="px-3 py-1.5 bg-industrial-900 border border-industrial-800 flex items-center gap-2">
          <span className="text-[10px] text-industrial-500 font-bold uppercase tracking-wider">ZONA:</span>
          <span className="text-[10px] font-black text-amber-500">{stats.active_zones}</span>
        </div>
        <div className="px-3 py-1.5 bg-industrial-900 border border-industrial-800 flex items-center gap-2">
          <span className="text-[10px] text-industrial-500 font-bold uppercase tracking-wider">ALERT:</span>
          <span className="text-[10px] font-black text-red-500">{stats.today_alerts}</span>
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

      {/* Three Column Layout - Height maximized */}
      <div className="flex gap-4 h-[calc(100vh-140px)] flex-col lg:flex-row items-stretch overflow-hidden">
        {/* Left Panel - Zone Editor */}
        <div className="w-full lg:w-[20%] min-w-[280px] flex flex-col h-full bg-industrial-900 border border-industrial-800 overflow-hidden">
          <ZoneEditor
            zones={zones}
            onRefresh={fetchZones}
            onStartDrawing={() => setDrawingMode(true)}
            drawingMode={drawingMode}
          />
        </div>

        {/* Center - Video Canvas (The Leader) */}
        <div className="flex-1 lg:w-[55%] flex flex-col h-full overflow-hidden relative group">
          <VideoCanvas
            zones={zones}
            drawingMode={drawingMode}
            onZoneCreated={handleZoneCreated}
            alertFlash={alertFlash}
          />
        </div>

        {/* Right Panel - Alert Feed */}
        <div className="w-full lg:w-[25%] min-w-[320px] flex flex-col h-full bg-industrial-900 border border-industrial-800 overflow-hidden">
          <AlertFeed onAlert={handleAlert} onShutdown={handleShutdown} />
        </div>
      </div>

      {/* Zone Creation Dialog */}
      {showZoneDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-industrial-950/80">
          <div className="bg-industrial-900 border border-industrial-800 p-8 w-full max-w-sm animate-fade-in shadow-2xl">
            <h3 className="text-[11px] font-black text-white mb-6 uppercase tracking-[0.3em] flex items-center gap-3">
              <svg className="w-4 h-4 text-amber-500" fill="currentColor" viewBox="0 0 24 24"><path d="M3 5v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2H5c-1.11 0-2 .9-2 2zm12 4c0 1.66-1.34 3-3 3s-3-1.34-3-3 1.34-3 3-3 3 1.34 3 3zm-9 8c0-2 4-3.1 6-3.1s6 1.1 6 3.1v1H6v-1z"/></svg>
              ZONE CONFIGURATION
            </h3>

            <div className="space-y-6">
              <div>
                <label className="block text-[10px] font-bold text-industrial-500 uppercase tracking-widest mb-2">Zone Name</label>
                <input
                  type="text"
                  value={newZoneName}
                  onChange={(e) => setNewZoneName(e.target.value)}
                  placeholder="ID: WELLHEAD-ALPHA"
                  className="input-field font-mono text-xs"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-[10px] font-bold text-industrial-500 uppercase tracking-widest mb-2">Risk Level</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => setNewZoneRisk("high")}
                    className={`py-3 text-[10px] font-black tracking-widest uppercase transition-all border ${
                      newZoneRisk === "high"
                        ? "bg-red-600 border-red-500 text-white"
                        : "bg-industrial-950 border-industrial-800 text-industrial-500"
                    }`}
                  >
                    HIGH
                  </button>
                  <button
                    onClick={() => setNewZoneRisk("low")}
                    className={`py-3 text-[10px] font-black tracking-widest uppercase transition-all border ${
                      newZoneRisk === "low"
                        ? "bg-amber-500 border-amber-400 text-industrial-950"
                        : "bg-industrial-950 border-industrial-800 text-industrial-500"
                    }`}
                  >
                    LOW
                  </button>
                </div>
              </div>

              <div className="flex gap-2 pt-4">
                <button
                  onClick={() => {
                    setShowZoneDialog(false);
                    setPendingVertices(null);
                  }}
                  className="btn-ghost flex-1 text-[10px] uppercase font-bold"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveZone}
                  disabled={!newZoneName.trim()}
                  className="btn-primary flex-1 text-[10px] uppercase font-bold disabled:opacity-20"
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
