"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import AlertFeed from "@/components/AlertFeed";
import ZoneEditor from "@/components/ZoneEditor";
import ToastContainer, { showToast } from "@/components/Toast";
import Image from "next/image";
import { useTheme } from "@/components/ThemeProvider";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8001";

interface ZoneData { id: number; name: string; vertices: number[][]; color: string; active: boolean; risk_level: string; }
interface VideoJobData { id: number; filename: string; status: string; }

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
  const [newZoneRisk, setNewZoneRisk] = useState("high");
  const streamRef = useRef<HTMLImageElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);

  // Video mode state
  const [videoMode, setVideoMode] = useState(false);
  const [videoJobId, setVideoJobId] = useState<number | null>(null);
  const [showVideoSelector, setShowVideoSelector] = useState(false);
  const [videoJobs, setVideoJobs] = useState<VideoJobData[]>([]);

  // Browser camera state
  const [browserCamActive, setBrowserCamActive] = useState(false);
  const browserStreamRef = useRef<MediaStream | null>(null);
  const browserVideoRef = useRef<HTMLVideoElement>(null);
  const browserWsRef = useRef<WebSocket | null>(null);
  const browserCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const browserOutputRef = useRef<HTMLImageElement>(null);
  const browserFrameLoopRef = useRef<number | null>(null);

  const fetchZones = useCallback(async () => {
    try { const r = await fetch(`${API_URL}/polygons`); if (r.ok) setZones(await r.json()); } catch {}
  }, []);
  const fetchStats = useCallback(async () => {
    try { const r = await fetch(`${API_URL}/stats`); if (r.ok) setStats(await r.json()); } catch {}
  }, []);
  const checkCamera = useCallback(async () => {
    try { const r = await fetch(`${API_URL}/camera/status`); if (r.ok) { const d = await r.json(); setCameraOnline(d.status === "online" || d.status === "on"); } } catch {}
  }, []);

  const fetchVideoJobs = useCallback(async () => {
    try {
      const r = await fetch(`${API_URL}/video/jobs`);
      if (r.ok) {
        const jobs = await r.json();
        setVideoJobs(jobs.filter((j: VideoJobData) => j.status === "done"));
      }
    } catch {}
  }, []);

  useEffect(() => {
    fetchZones(); fetchStats(); checkCamera();
    const i1 = setInterval(fetchStats, 15000);
    const i2 = setInterval(checkCamera, 5000);
    const handleRefresh = () => fetchStats();
    window.addEventListener("siews-stats-refresh", handleRefresh);
    return () => { clearInterval(i1); clearInterval(i2); window.removeEventListener("siews-stats-refresh", handleRefresh); };
  }, [fetchZones, fetchStats, checkCamera]);

  const toggleCamera = async () => {
    // If in video mode, exit video mode first
    if (videoMode) { setVideoMode(false); setVideoJobId(null); }
    try {
      const ep = cameraOnline ? `${API_URL}/camera/disable` : `${API_URL}/camera/enable`;
      const r = await fetch(ep, { method: "POST" });
      if (r.ok) { const d = await r.json(); setCameraOnline(d.status === "on"); showToast({ message: d.status === "on" ? "Camera enabled" : "Camera disabled", type: "success" }); }
    } catch { showToast({ message: "Failed to toggle camera", type: "error" }); }
  };

  const openVideoSelector = async () => {
    await fetchVideoJobs();
    setShowVideoSelector(true);
  };

  const selectVideo = (jobId: number) => {
    setVideoJobId(jobId);
    setVideoMode(true);
    setCameraOnline(false); // Disable live camera when in video mode
    setShowVideoSelector(false);
    showToast({ message: "Video mode activated", type: "success" });
  };

  const exitVideoMode = () => {
    setVideoMode(false);
    setVideoJobId(null);
  };

  // Browser Camera functions
  const startBrowserCam = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: "environment" }
      });
      browserStreamRef.current = stream;

      // Hidden video element to capture frames
      const vid = document.createElement("video");
      vid.srcObject = stream;
      vid.muted = true;
      vid.playsInline = true;
      await vid.play();
      (browserVideoRef as any).current = vid;

      // Canvas for frame capture
      const canvas = document.createElement("canvas");
      canvas.width = 640;
      canvas.height = 480;
      browserCanvasRef.current = canvas;

      // WebSocket to backend
      const ws = new WebSocket(`${WS_URL}/ws/camera`);
      ws.binaryType = "arraybuffer";
      browserWsRef.current = ws;

      ws.onopen = () => {
        setBrowserCamActive(true);
        setVideoMode(false);
        setCameraOnline(false);
        showToast({ message: "Browser camera connected", type: "success" });
        // Start sending frames after short delay
        setTimeout(sendBrowserFrame, 200);
      };

      ws.onmessage = (event) => {
        // Receive annotated frame from backend
        if (browserOutputRef.current && event.data instanceof ArrayBuffer) {
          const blob = new Blob([event.data], { type: "image/jpeg" });
          const url = URL.createObjectURL(blob);
          const prev = browserOutputRef.current.src;
          browserOutputRef.current.src = url;
          if (prev && prev.startsWith("blob:")) URL.revokeObjectURL(prev);
        }
      };

      ws.onclose = () => {
        if (browserCamActive) {
          setBrowserCamActive(false);
          showToast({ message: "Browser camera disconnected", type: "info" });
        }
      };

      ws.onerror = () => {
        showToast({ message: "Browser camera connection failed", type: "error" });
        stopBrowserCam();
      };
    } catch (err) {
      showToast({ message: "Cannot access camera. Check browser permissions.", type: "error" });
    }
  };

  const sendBrowserFrame = () => {
    const vid = (browserVideoRef as any).current;
    const canvas = browserCanvasRef.current;
    const ws = browserWsRef.current;

    if (!vid || !canvas || !ws || ws.readyState !== WebSocket.OPEN) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Match canvas to actual video dimensions
    if (vid.videoWidth && vid.videoHeight) {
      canvas.width = vid.videoWidth;
      canvas.height = vid.videoHeight;
    }

    ctx.drawImage(vid, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (blob && ws.readyState === WebSocket.OPEN) {
        blob.arrayBuffer().then((buf) => ws.send(buf));
      }
      // Send next frame after 150ms (~6-7fps, gives backend time to process)
      browserFrameLoopRef.current = window.setTimeout(sendBrowserFrame, 150);
    }, "image/jpeg", 0.6);
  };

  const stopBrowserCam = () => {
    if (browserFrameLoopRef.current) {
      clearTimeout(browserFrameLoopRef.current);
      browserFrameLoopRef.current = null;
    }
    if (browserWsRef.current) {
      browserWsRef.current.close();
      browserWsRef.current = null;
    }
    if (browserStreamRef.current) {
      browserStreamRef.current.getTracks().forEach(t => t.stop());
      browserStreamRef.current = null;
    }
    setBrowserCamActive(false);
  };

  const toggleAll = () => { const n = !panelsVisible; setPanelsVisible(n); setLeftOpen(n); setRightOpen(n); };
  const startDrawing = () => {
    setDrawingMode(true); setDrawPoints([]); setLeftOpen(false); setRightOpen(false); setPanelsVisible(false);
    // Pause video when entering drawing mode
    if (videoRef.current) videoRef.current.pause();
  };
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
      if (r.ok) { showToast({ message: `Zone "${newZoneName}" created`, type: "success" }); fetchZones(); }
    } catch { showToast({ message: "Failed to create zone", type: "error" }); }
    setShowZoneDialog(false); setNewZoneName(""); setNewZoneRisk("high"); cancelDrawing();
  };

  // Draw zone overlay on canvas
  useEffect(() => {
    if (!overlayRef.current) return;
    const canvas = overlayRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const parent = canvas.parentElement;
    if (!parent) return;
    canvas.width = parent.clientWidth; canvas.height = parent.clientHeight;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw existing zones
    zones.forEach((zone) => {
      if (!zone.active || zone.vertices.length < 3) return;
      ctx.beginPath();
      zone.vertices.forEach(([x, y], i) => {
        const px = x * canvas.width;
        const py = y * canvas.height;
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      });
      ctx.closePath();
      const color = zone.risk_level === "high" ? "rgba(239,68,68," : "rgba(251,191,36,";
      ctx.fillStyle = color + "0.08)";
      ctx.fill();
      ctx.strokeStyle = color + "0.6)";
      ctx.lineWidth = 1.5;
      ctx.stroke();
      // Zone label
      const [lx, ly] = zone.vertices[0];
      ctx.font = "bold 10px Poppins, sans-serif";
      ctx.fillStyle = color + "0.9)";
      ctx.fillText(zone.name, lx * canvas.width + 4, ly * canvas.height - 4);
    });

    // Draw new zone points
    if (drawPoints.length === 0) return;
    ctx.strokeStyle = "#2a8fd4"; ctx.lineWidth = 2; ctx.setLineDash([6, 4]);
    ctx.beginPath();
    drawPoints.forEach(([x, y], i) => { const px = (x/100)*canvas.width; const py = (y/100)*canvas.height; if (i===0) ctx.moveTo(px,py); else ctx.lineTo(px,py); });
    if (drawPoints.length > 2) { ctx.closePath(); ctx.fillStyle = "rgba(42,143,212,0.1)"; ctx.fill(); }
    ctx.stroke(); ctx.setLineDash([]);
    drawPoints.forEach(([x, y]) => { const px = (x/100)*canvas.width; const py = (y/100)*canvas.height; ctx.beginPath(); ctx.arc(px,py,4,0,Math.PI*2); ctx.fillStyle="#2a8fd4"; ctx.fill(); ctx.strokeStyle="#fff"; ctx.lineWidth=1.5; ctx.stroke(); });
  }, [drawPoints, zones, videoMode, cameraOnline]);

  const handleAlert = useCallback(() => { fetchStats(); }, [fetchStats]);
  const handleShutdown = useCallback(() => {}, []);

  // Real-time video playback detection — check frame against zones periodically
  useEffect(() => {
    if (!videoMode || !videoJobId || drawingMode) return;
    const video = videoRef.current;
    if (!video) return;

    let lastCheckedTime = -1;
    const checkInterval = setInterval(async () => {
      if (!video || video.paused || video.ended) return;
      const currentTime = Math.round(video.currentTime * 2) / 2; // Round to 0.5s
      if (currentTime === lastCheckedTime) return;
      lastCheckedTime = currentTime;

      try {
        const r = await fetch(`${API_URL}/video/jobs/${videoJobId}/check-frame?timestamp=${currentTime}`);
        if (!r.ok) return;
        const data = await r.json();
        if (data.violations && data.violations.length > 0) {
          // Create alert for each violation via backend
          for (const v of data.violations) {
            const alertRes = await fetch(`${API_URL}/video/alert`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                job_id: videoJobId,
                zone_id: v.zone_id,
                zone_name: v.zone_name,
                risk_level: v.risk_level,
                confidence: v.confidence,
                violation_type: v.type,
                timestamp_sec: data.timestamp_sec,
              }),
            });
            if (alertRes.ok) {
              // Alert will come via WebSocket
            }
          }
        }
      } catch {}
    }, 1000); // Check every 1 second

    return () => clearInterval(checkInterval);
  }, [videoMode, videoJobId, drawingMode]);

  // Determine what's active: camera, video, browser cam, or nothing
  const hasActiveSource = cameraOnline || videoMode || browserCamActive;

  return (
    <div className="fixed inset-0 overflow-hidden" style={{ background: "var(--bg-base)" }}>
      {/* Fullscreen Video/Camera Area */}
      <div
        className="absolute inset-0 z-0 flex items-center justify-center"
        style={{ background: "var(--bg-base)", cursor: drawingMode ? "crosshair" : "default" }}
        onClick={handleStreamClick}
        onDoubleClick={handleStreamDoubleClick}
      >
        {browserCamActive ? (
          <>
            <img ref={browserOutputRef} alt="Browser Camera" className="w-full h-full object-contain" />
            <canvas ref={overlayRef} className="absolute inset-0 w-full h-full pointer-events-none" />
          </>
        ) : cameraOnline && !videoMode ? (
          <>
            <img ref={streamRef} src={`${API_URL}/stream`} alt="Live" className="w-full h-full object-contain" onError={() => { setCameraOnline(false); setTimeout(() => { if (streamRef.current) streamRef.current.src = `${API_URL}/stream?t=${Date.now()}`; }, 5000); }} />
            <canvas ref={overlayRef} className="absolute inset-0 w-full h-full pointer-events-none" />
          </>
        ) : videoMode && videoJobId ? (
          <>
            <video
              ref={videoRef}
              src={`${API_URL}/video/annotated/${videoJobId}`}
              className={`w-full h-full object-contain ${drawingMode ? "pointer-events-none" : ""}`}
              controls={!drawingMode}
              autoPlay
              playsInline
            />
            <canvas ref={overlayRef} className={`absolute inset-0 w-full h-full ${drawingMode ? "pointer-events-auto" : "pointer-events-none"}`} />
          </>
        ) : (
          <div className="flex flex-col items-center justify-center">
            <Image src="/logo-siews.png" alt="SIEWS+" width={64} height={64} className="opacity-15 mb-6" />
            <p className="text-sm font-medium mb-1" style={{ color: "var(--text-muted)" }}>No active source</p>
            <p className="text-xs" style={{ color: "var(--text-faint)" }}>Click Cam On, Browser Cam, or Open Video</p>
          </div>
        )}
      </div>

      {/* Navbar */}
      {!drawingMode && (
      <div className="fixed top-4 left-4 right-4 z-50 pointer-events-none">
        <header className="pointer-events-auto flex items-center justify-between px-5 h-12 backdrop-blur-2xl border rounded-full shadow-lg max-w-[1400px] mx-auto" style={{ background: "var(--bg-glass)", borderColor: "var(--border)" }}>
          <a href="/" className="flex items-center gap-2">
            <Image src="/logo-siews.png" alt="SIEWS+" width={22} height={22} className="rounded-md" />
            <span className="text-xs font-semibold hidden sm:block" style={{ color: "var(--text-main)" }}>SIEWS+</span>
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
            <button onClick={browserCamActive ? stopBrowserCam : startBrowserCam} className={`px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-all ${browserCamActive ? "text-emerald-400 bg-emerald-500/10" : "hover:bg-[var(--border)]"}`} style={!browserCamActive ? { color: "var(--text-muted)" } : undefined}>
              {browserCamActive ? "🟢 Browser Cam" : "Browser Cam"}
            </button>
            <button onClick={openVideoSelector} className={`px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-all ${videoMode ? "text-purple-400 bg-purple-500/10" : "hover:bg-[var(--border)]"}`} style={!videoMode ? { color: "var(--text-muted)" } : undefined}>
              {videoMode ? "Video On" : "Open Video"}
            </button>
            {videoMode && (
              <button onClick={exitVideoMode} className="px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-all text-red-400 bg-red-500/10">✕</button>
            )}
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
            <span className={`status-dot ${hasActiveSource ? "online" : "offline"}`} />
          </div>
        </header>
      </div>
      )}

      {/* Floating Panels */}
      <div className="absolute inset-0 z-10 pointer-events-none">
        <div className="h-full flex items-center justify-between px-5 max-w-[1920px] mx-auto">
          {/* LEFT — Zones */}
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
          {/* RIGHT — Alerts */}
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

      {/* Source badge */}
      {hasActiveSource && (
        <div className="fixed bottom-3 left-5 z-20 flex items-center gap-2 px-2.5 py-1 rounded-md backdrop-blur border" style={{ background: "var(--bg-glass)", borderColor: "var(--border)" }}>
          {browserCamActive ? (
            <>
              <div className="relative"><div className="w-1.5 h-1.5 rounded-full bg-emerald-500" /><div className="absolute inset-0 w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping opacity-60" /></div>
              <span className="text-[10px]" style={{ color: "var(--text-main)" }}>BROWSER CAM</span>
            </>
          ) : cameraOnline && !videoMode ? (
            <>
              <div className="relative"><div className="w-1.5 h-1.5 rounded-full bg-red-500" /><div className="absolute inset-0 w-1.5 h-1.5 rounded-full bg-red-500 animate-ping opacity-60" /></div>
              <span className="text-[10px]" style={{ color: "var(--text-main)" }}>LIVE</span>
            </>
          ) : videoMode ? (
            <>
              <div className="w-1.5 h-1.5 rounded-full bg-purple-500" />
              <span className="text-[10px]" style={{ color: "var(--text-main)" }}>VIDEO</span>
            </>
          ) : null}
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

      {/* Video Selector Dialog */}
      {showVideoSelector && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setShowVideoSelector(false)} />
          <div className="relative z-10 p-6 w-[420px] max-h-[70vh] rounded-2xl border shadow-2xl animate-fade-in overflow-hidden flex flex-col" style={{ background: "var(--bg-surface)", borderColor: "var(--border)" }}>
            <h3 className="text-base font-semibold mb-1" style={{ color: "var(--text-main)" }}>Open Video</h3>
            <p className="text-xs mb-4" style={{ color: "var(--text-muted)" }}>Select a processed video to display in dashboard with full zone & alert features.</p>
            <div className="flex-1 overflow-y-auto space-y-2">
              {videoJobs.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-sm" style={{ color: "var(--text-faint)" }}>No processed videos available</p>
                  <p className="text-xs mt-1" style={{ color: "var(--text-faint)" }}>Upload and process a video in Settings first</p>
                </div>
              ) : (
                videoJobs.map((job) => (
                  <button
                    key={job.id}
                    onClick={() => selectVideo(job.id)}
                    className="w-full text-left p-3 rounded-lg border transition-all hover:border-[var(--accent)]/40 hover:bg-[var(--accent)]/5"
                    style={{ borderColor: "var(--border)", background: "var(--bg-input)" }}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2.5">
                        <svg className="w-4 h-4 text-purple-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                        <span className="text-sm font-medium truncate max-w-[250px]" style={{ color: "var(--text-main)" }}>{job.filename}</span>
                      </div>
                      <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-400">Ready</span>
                    </div>
                  </button>
                ))
              )}
            </div>
            <div className="mt-4 pt-3 border-t" style={{ borderColor: "var(--border)" }}>
              <button onClick={() => setShowVideoSelector(false)} className="w-full py-2.5 rounded-lg text-sm font-medium transition-all" style={{ background: "var(--bg-input)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>Cancel</button>
            </div>
          </div>
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

      <ToastContainer />
    </div>
  );
}
