"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import AlertFeed from "@/components/AlertFeed";
import ZoneEditor from "@/components/ZoneEditor";
import ToastContainer, { showToast } from "@/components/Toast";
import Image from "next/image";
import { useTheme } from "@/components/ThemeProvider";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface ZoneData { id: number; name: string; vertices: number[][]; color: string; active: boolean; risk_level: string; }

export default function DashboardPage() {
  const { theme, toggleTheme } = useTheme();
  const [zones, setZones] = useState<ZoneData[]>([]);
  const [panelsVisible, setPanelsVisible] = useState(true);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [cameraOnline, setCameraOnline] = useState(false);
  const [drawingMode, setDrawingMode] = useState(false);
  const [drawPoints, setDrawPoints] = useState<number[][]>([]);
  const [stats, setStats] = useState({ active_zones: 0, today_alerts: 0, unresolved_alerts: 0 });
  const [showZoneDialog, setShowZoneDialog] = useState(false);
  const [newZoneName, setNewZoneName] = useState("");
  const [showVideoPlayer, setShowVideoPlayer] = useState(false);
  const [videoJobs, setVideoJobs] = useState<any[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<string | null>(null);
  const [newZoneRisk, setNewZoneRisk] = useState("high");
  const streamRef = useRef<HTMLImageElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);

  const fetchZones = useCallback(async () => {
    try { const r = await fetch(`${API_URL}/polygons`); if (r.ok) setZones(await r.json()); } catch {}
  }, []);
  const fetchStats = useCallback(async () => {
    try { const r = await fetch(`${API_URL}/stats`); if (r.ok) setStats(await r.json()); } catch {}
  }, []);
  const checkCamera = useCallback(async () => {
    try { const r = await fetch(`${API_URL}/camera/status`); if (r.ok) { const d = await r.json(); setCameraOnline(d.status === "online" || d.status === "on"); } } catch {}
  }, []);

  useEffect(() => {
    fetchZones(); fetchStats(); checkCamera();
    const i1 = setInterval(fetchStats, 15000);
    const i2 = setInterval(checkCamera, 5000);
    const handleRefresh = () => fetchStats();
    window.addEventListener("siews-stats-refresh", handleRefresh);
    return () => { clearInterval(i1); clearInterval(i2); window.removeEventListener("siews-stats-refresh", handleRefresh); };
  }, [fetchZones, fetchStats, checkCamera]);

  // Fetch video jobs when video player opens
  useEffect(() => {
    if (!showVideoPlayer) return;
    fetch(`${API_URL}/video/jobs`).then(r => r.ok ? r.json() : []).then(setVideoJobs).catch(() => {});
  }, [showVideoPlayer]);

  const toggleCamera = async () => {
    try {
      const ep = cameraOnline ? `${API_URL}/camera/disable` : `${API_URL}/camera/enable`;
      const r = await fetch(ep, { method: "POST" });
      if (r.ok) { const d = await r.json(); setCameraOnline(d.status === "on"); showToast(d.status === "on" ? "Camera enabled" : "Camera disabled", "success"); }
    } catch { showToast("Failed to toggle camera", "error"); }
  };

  const toggleAll = () => { const n = !panelsVisible; setPanelsVisible(n); setLeftOpen(n); setRightOpen(n); };
  const startDrawing = () => { setDrawingMode(true); setDrawPoints([]); setLeftOpen(false); setRightOpen(false); setPanelsVisible(false); };
  const cancelDrawing = () => { setDrawingMode(false); setDrawPoints([]); setPanelsVisible(true); setLeftOpen(true); setRightOpen(true); };

  const handleStreamClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!drawingMode) return;
    const rect = e.currentTarget.getBoundingClientRect();
    setDrawPoints((prev) => [...prev, [((e.clientX - rect.left) / rect.width) * 100, ((e.clientY - rect.top) / rect.height) * 100]]);
  };

  const handleStreamDoubleClick = () => {
    if (!drawingMode || drawPoints.length < 3) return;
    setShowZoneDialog(true);
  };

  const saveZone = async () => {
    if (!newZoneName.trim()) return;
    try {
      const nv = drawPoints.map(([x, y]) => [x / 100, y / 100]);
      const r = await fetch(`${API_URL}/polygons`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newZoneName, vertices: nv, color: newZoneRisk === "high" ? "#ef4444" : "#fbbf24", active: true, risk_level: newZoneRisk }),
      });
      if (r.ok) { showToast(`Zone "${newZoneName}" created`, "success"); fetchZones(); }
    } catch { showToast("Failed to create zone", "error"); }
    setShowZoneDialog(false); setNewZoneName(""); setNewZoneRisk("high"); cancelDrawing();
  };

  useEffect(() => {
    if (!overlayRef.current) return;
    const canvas = overlayRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const parent = canvas.parentElement;
    if (!parent) return;
    canvas.width = parent.clientWidth; canvas.height = parent.clientHeight;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (drawPoints.length === 0) return;
    ctx.strokeStyle = "#2a8fd4"; ctx.lineWidth = 2; ctx.setLineDash([6, 4]);
    ctx.beginPath();
    drawPoints.forEach(([x, y], i) => { const px = (x/100)*canvas.width; const py = (y/100)*canvas.height; if (i===0) ctx.moveTo(px,py); else ctx.lineTo(px,py); });
    if (drawPoints.length > 2) { ctx.closePath(); ctx.fillStyle = "rgba(42,143,212,0.1)"; ctx.fill(); }
    ctx.stroke(); ctx.setLineDash([]);
    drawPoints.forEach(([x, y]) => { const px = (x/100)*canvas.width; const py = (y/100)*canvas.height; ctx.beginPath(); ctx.arc(px,py,4,0,Math.PI*2); ctx.fillStyle="#2a8fd4"; ctx.fill(); ctx.strokeStyle="#fff"; ctx.lineWidth=1.5; ctx.stroke(); });
  }, [drawPoints]);

  const handleAlert = useCallback(() => { fetchStats(); }, [fetchStats]);
  const handleShutdown = useCallback(() => {}, []);

  const navLinkStyle = { color: "var(--text-muted)" };

  return (
    <div className="fixed inset-0 overflow-hidden" style={{ background: "var(--bg-base)" }}>
      {/* Fullscreen Camera */}
      <div
        className="absolute inset-0 z-0 flex items-center justify-center"
        style={{ background: cameraOnline ? "var(--bg-base)" : "var(--bg-base)", cursor: drawingMode ? "crosshair" : "default" }}
        onClick={handleStreamClick}
        onDoubleClick={handleStreamDoubleClick}
      >
        {cameraOnline ? (
          <>
            <img ref={streamRef} src={`${API_URL}/stream`} alt="Live" className="w-full h-full object-contain" onError={() => { setTimeout(() => { if (streamRef.current) streamRef.current.src = `${API_URL}/stream?t=${Date.now()}`; }, 2000); }} />
            <canvas ref={overlayRef} className="absolute inset-0 w-full h-full pointer-events-none" />
          </>
        ) : (
          <div className="flex flex-col items-center justify-center">
            <Image src="/logo-siews.png" alt="SIEWS+" width={64} height={64} className="opacity-15 mb-6" />
            <p className="text-sm font-medium mb-1" style={{ color: "var(--text-muted)" }}>Camera is turned off</p>
            <p className="text-xs" style={{ color: "var(--text-faint)" }}>Click Cam On to enable the live feed</p>
          </div>
        )}
      </div>

      {/* Navbar */}
      {!drawingMode && (
      <div className="fixed top-4 left-4 right-4 z-50 pointer-events-none">
        <header className="pointer-events-auto flex items-center justify-between px-5 h-12 backdrop-blur-2xl border rounded-full shadow-lg max-w-[1400px] mx-auto" style={{ background: "var(--bg-glass)", borderColor: "var(--border)" }}>
          <a href="/" className="flex items-center gap-2.5">
            <Image src="/logo-siews.png" alt="SIEWS+" width={30} height={30} className="rounded-lg" />
            <span className="text-sm font-semibold hidden sm:block" style={{ color: "var(--text-main)" }}>SIEWS+</span>
          </a>
          <nav className="flex items-center gap-0.5">
            <a href="/dashboard" className="px-3.5 py-1.5 rounded-lg text-[12px] font-medium text-sky-400 bg-sky-500/10">Dashboard</a>
            <a href="/faces" className="px-3.5 py-1.5 rounded-lg text-[12px] font-medium transition-all hover:bg-[var(--border)]" style={{ color: "var(--text-muted)" }}>Personnel</a>
            <a href="/incidents" className="px-3.5 py-1.5 rounded-lg text-[12px] font-medium transition-all hover:bg-[var(--border)]" style={{ color: "var(--text-muted)" }}>
              Incidents
              {stats.unresolved_alerts > 0 && <span className="ml-1.5 inline-flex items-center justify-center min-w-[16px] h-[16px] rounded-full bg-red-500 text-white text-[9px] font-bold px-1">{stats.unresolved_alerts > 9 ? "9+" : stats.unresolved_alerts}</span>}
            </a>
            <a href="/zones" className="px-3.5 py-1.5 rounded-lg text-[12px] font-medium transition-all hover:bg-[var(--border)]" style={{ color: "var(--text-muted)" }}>Zones</a>
            <a href="/settings" className="px-3.5 py-1.5 rounded-lg text-[12px] font-medium transition-all hover:bg-[var(--border)]" style={{ color: "var(--text-muted)" }}>Settings</a>
            <div className="w-px h-5 mx-2" style={{ background: "var(--border)" }} />
            <button onClick={toggleCamera} className={`px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-all ${cameraOnline ? "text-emerald-400 bg-emerald-500/10" : "text-red-400 bg-red-500/10"}`}>{cameraOnline ? "Cam On" : "Cam Off"}</button>
            <button onClick={async () => { setShowVideoPlayer(true); try { const r = await fetch(`${API_URL}/video/jobs`); if (r.ok) setVideoJobs(await r.json()); } catch {} }} className="px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-all text-purple-400 bg-purple-500/10 hover:bg-purple-500/20">Video</button>
            <button onClick={toggleAll} className="px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-all hover:bg-[var(--border)]" style={{ color: "var(--text-muted)" }}>{panelsVisible ? "Close All" : "Open All"}</button>
          </nav>
          <div className="flex items-center gap-2">
            <button onClick={toggleTheme} className="p-2 rounded-lg transition-all hover:bg-[var(--border)]" style={{ color: "var(--text-muted)" }} title="Toggle theme">
              {theme === "dark" ? (
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" /></svg>
              ) : (
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" /></svg>
              )}
            </button>
            <span className={`status-dot ${cameraOnline ? "online" : "offline"}`} />
          </div>
        </header>
      </div>
      )}

      {/* Floating Panels */}
      <div className="absolute inset-0 z-10 pointer-events-none">
        <div className="h-full flex items-center justify-between px-5 max-w-[1920px] mx-auto">
          {/* LEFT */}
          <div className="pointer-events-auto ml-2">
            {leftOpen && panelsVisible ? (
              <div className="glass-card w-[240px] max-h-[60vh] overflow-y-auto animate-slide-in">
                <div className="flex items-center justify-between px-3 py-2.5 border-b" style={{ borderColor: "var(--border)" }}>
                  <span className="text-[11px] font-semibold" style={{ color: "var(--text-main)" }}>Zones</span>
                  <button onClick={() => setLeftOpen(false)} style={{ color: "var(--text-faint)" }}>
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>
                <ZoneEditor zones={zones} onRefresh={fetchZones} onStartDrawing={startDrawing} drawingMode={drawingMode} />
              </div>
            ) : (
              <button onClick={() => { setLeftOpen(true); setPanelsVisible(true); }} className="glass-card p-2 opacity-60 hover:opacity-100 transition-opacity" title="Zones">
                <svg className="w-4 h-4" style={{ color: "var(--accent-light)" }} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" /></svg>
              </button>
            )}
          </div>
          <div className="flex-1" />
          {/* RIGHT */}
          <div className="pointer-events-auto mr-2">
            {rightOpen && panelsVisible ? (
              <div className="glass-card w-[260px] max-h-[60vh] overflow-hidden flex flex-col animate-slide-in">
                <div className="flex items-center justify-between px-3 py-2.5 border-b" style={{ borderColor: "var(--border)" }}>
                  <span className="text-[11px] font-semibold" style={{ color: "var(--text-main)" }}>Alerts</span>
                  <button onClick={() => setRightOpen(false)} style={{ color: "var(--text-faint)" }}>
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>
                <AlertFeed onAlert={handleAlert} onShutdown={handleShutdown} />
              </div>
            ) : (
              <button onClick={() => { setRightOpen(true); setPanelsVisible(true); }} className="glass-card p-2 opacity-60 hover:opacity-100 transition-opacity" title="Alerts">
                <svg className="w-4 h-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" /></svg>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Live badge */}
      {cameraOnline && (
        <div className="fixed bottom-3 left-5 z-20 flex items-center gap-2 px-2.5 py-1 rounded-md backdrop-blur border" style={{ background: "var(--bg-glass)", borderColor: "var(--border)" }}>
          <div className="relative"><div className="w-1.5 h-1.5 rounded-full bg-red-500" /><div className="absolute inset-0 w-1.5 h-1.5 rounded-full bg-red-500 animate-ping opacity-60" /></div>
          <span className="text-[10px]" style={{ color: "var(--text-main)" }}>LIVE</span>
        </div>
      )}

      {/* Drawing indicator */}
      {drawingMode && (
        <div className="fixed bottom-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-3 px-4 py-2 rounded-lg backdrop-blur border" style={{ background: "var(--bg-glass)", borderColor: "var(--accent)" }}>
          <div className="w-1.5 h-1.5 rounded-full bg-sky-400 animate-pulse" />
          <span className="text-[11px]" style={{ color: "var(--text-main)" }}>Click to place points (min 3) — double-click or Enter to finish</span>
          <button onClick={cancelDrawing} className="text-[11px] px-2 py-0.5 rounded" style={{ color: "var(--text-muted)", background: "var(--bg-input)" }}>Cancel</button>
        </div>
      )}

      {/* Zone creation dialog */}
      {showZoneDialog && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => { setShowZoneDialog(false); cancelDrawing(); }} />
          <div className="relative z-10 p-6 w-[360px] rounded-2xl border shadow-2xl animate-fade-in" style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
            <h3 className="text-base font-semibold mb-4" style={{ color: "var(--text-main)" }}>Create Zone</h3>
            <div className="space-y-4">
              <div>
                <label className="text-xs font-medium mb-1.5 block" style={{ color: "var(--text-muted)" }}>Zone Name</label>
                <input value={newZoneName} onChange={(e) => setNewZoneName(e.target.value)} placeholder="e.g. Wellhead Area" className="input-field text-sm" autoFocus />
              </div>
              <div>
                <label className="text-xs font-medium mb-2 block" style={{ color: "var(--text-muted)" }}>Risk Level</label>
                <div className="flex gap-3">
                  <button type="button" onClick={() => setNewZoneRisk("high")} className={`flex-1 py-2.5 rounded-lg text-xs font-medium border transition-all ${newZoneRisk === "high" ? "border-red-500/40 bg-red-500/10 text-red-400" : ""}`} style={newZoneRisk !== "high" ? { borderColor: "var(--border)", color: "var(--text-faint)" } : undefined}>High Risk</button>
                  <button type="button" onClick={() => setNewZoneRisk("low")} className={`flex-1 py-2.5 rounded-lg text-xs font-medium border transition-all ${newZoneRisk === "low" ? "border-amber-500/40 bg-amber-500/10 text-amber-400" : ""}`} style={newZoneRisk !== "low" ? { borderColor: "var(--border)", color: "var(--text-faint)" } : undefined}>Low Risk</button>
                </div>
              </div>
              <div className="flex gap-3 pt-2">
                <button onClick={() => { setShowZoneDialog(false); cancelDrawing(); }} className="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all" style={{ background: "var(--bg-input)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>Cancel</button>
                <button onClick={saveZone} disabled={!newZoneName.trim()} className="flex-1 py-2.5 rounded-lg text-sm font-medium text-white transition-all disabled:opacity-30" style={{ background: "var(--accent)" }}>Create</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Video Player Modal */}
      {showVideoPlayer && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm">
          <div className="w-full max-w-md mx-4 rounded-xl overflow-hidden border" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
            <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: "var(--border)" }}>
              <h3 className="text-sm font-semibold" style={{ color: "var(--text-main)" }}>Simulate Video as Live Feed</h3>
              <button onClick={() => setShowVideoPlayer(false)} className="text-xs px-2 py-1 rounded hover:bg-[var(--border)]" style={{ color: "var(--text-muted)" }}>✕</button>
            </div>
            <div className="p-4 space-y-2 max-h-[50vh] overflow-y-auto">
              <p className="text-[11px] mb-3" style={{ color: "var(--text-faint)" }}>Select a processed video to play as live camera feed. All detections, zone alerts, and WhatsApp notifications will trigger as if real.</p>
              {videoJobs.filter((j: any) => j.status === "done").length === 0 ? (
                <p className="text-center py-6 text-xs" style={{ color: "var(--text-faint)" }}>No videos ready. Upload via Settings → Video Processing.</p>
              ) : (
                videoJobs.filter((j: any) => j.status === "done").map((job: any) => (
                  <button key={job.id} onClick={async () => {
                    try {
                      const r = await fetch(`${API_URL}/stream/simulate-video?job_id=${job.id}`, { method: "POST" });
                      if (r.ok) {
                        setCameraOnline(true);
                        setShowVideoPlayer(false);
                        // Force reload stream after small delay to let backend start serving video
                        setTimeout(() => { if (streamRef.current) streamRef.current.src = `${API_URL}/stream?t=${Date.now()}`; }, 500);
                        showToast({ message: `Playing "${job.filename}" as live feed`, type: "success" });
                      }
                      else showToast({ message: "Failed to start simulation", type: "error" });
                    } catch { showToast({ message: "Error", type: "error" }); }
                  }}
                    className="w-full text-left p-3 rounded-lg border transition-all hover:border-purple-500/30 hover:bg-purple-500/5" style={{ background: "var(--bg-input)", borderColor: "var(--border)" }}>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium truncate" style={{ color: "var(--text-main)" }}>{job.filename}</span>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-purple-500/15 text-purple-400">▶ Play</span>
                    </div>
                    <p className="text-[10px] mt-1" style={{ color: "var(--text-faint)" }}>{new Date(job.created_at).toLocaleString()}</p>
                  </button>
                ))
              )}
              {/* Stop simulation button */}
              <button onClick={async () => {
                await fetch(`${API_URL}/stream/reset`, { method: "POST" });
                setShowVideoPlayer(false);
                showToast({ message: "Simulation stopped, back to live camera", type: "info" });
              }} className="w-full mt-3 py-2 rounded-lg text-xs font-medium border border-red-500/20 text-red-400 hover:bg-red-500/10 transition-all">
                Stop Simulation → Back to Live
              </button>
            </div>
          </div>
        </div>
      )}

      <ToastContainer />
    </div>
  );
}
