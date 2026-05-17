"use client";

import { useEffect, useRef, useState, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface FrameDetection {
  frame: number;
  timestamp_sec: number;
  persons: { bbox: number[]; confidence: number; ppe_violations?: string[] }[];
  env: { class_name: string; confidence: number; bbox: number[] }[];
  vehicles: { class_name: string; confidence: number; bbox: number[] }[];
  road?: { class_name: string; confidence: number; bbox: number[] }[];
  safety_cones?: { class_name: string; confidence: number; bbox: number[] }[];
  has_violation: boolean;
}

interface SimZone {
  id: string;
  name: string;
  vertices: number[][]; // normalized [0-1]
  color: string;
  risk_level: string;
}

interface VideoSimPlayerProps {
  jobId: number;
  filename: string;
  onAlert?: (msg: string) => void;
}

export default function VideoSimPlayer({ jobId, filename, onAlert }: VideoSimPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [frameData, setFrameData] = useState<FrameDetection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fps, setFps] = useState(25);

  // Zone drawing state
  const [zones, setZones] = useState<SimZone[]>([]);
  const [dbZones, setDbZones] = useState<SimZone[]>([]);
  const [showDbZones, setShowDbZones] = useState(true);
  const [drawingMode, setDrawingMode] = useState(false);
  const [currentVertices, setCurrentVertices] = useState<number[][]>([]);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);
  const [violations, setViolations] = useState<string[]>([]);
  const [showDetections, setShowDetections] = useState(true);

  // Alert cooldown to avoid spam
  const alertCooldownRef = useRef<Record<string, number>>({});

  // Load zones from database (same as dashboard)
  useEffect(() => {
    const loadZones = async () => {
      try {
        const res = await fetch(`${API_URL}/polygons`);
        if (res.ok) {
          const data = await res.json();
          const mapped: SimZone[] = data
            .filter((z: any) => z.active)
            .map((z: any) => ({
              id: `db_${z.id}`,
              name: z.name,
              vertices: z.vertices,
              color: z.color,
              risk_level: z.risk_level,
            }));
          setDbZones(mapped);
        }
      } catch {}
    };
    loadZones();
  }, []);

  // Combined zones (database + local simulation)
  const allZones = [...(showDbZones ? dbZones : []), ...zones];

  // Load frame detection data
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_URL}/video/jobs/${jobId}/result`);
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Failed to load video data");
        }
        const data = await res.json();
        setFrameData(data.frames || []);
        // Estimate FPS from frame data
        if (data.frames && data.frames.length > 1) {
          const lastFrame = data.frames[data.frames.length - 1];
          const estimatedFps = Math.round(lastFrame.frame / lastFrame.timestamp_sec);
          if (estimatedFps > 0) setFps(estimatedFps);
        }
      } catch (e: any) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [jobId]);

  // Resize canvas to match video
  const updateCanvasSize = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    const rect = video.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      canvas.width = rect.width;
      canvas.height = rect.height;
    }
  }, []);

  useEffect(() => {
    updateCanvasSize();
    window.addEventListener("resize", updateCanvasSize);
    
    // ResizeObserver for container size changes (more reliable than resize event)
    const container = containerRef.current;
    let resizeObserver: ResizeObserver | null = null;
    if (container) {
      resizeObserver = new ResizeObserver(() => {
        setTimeout(updateCanvasSize, 50);
      });
      resizeObserver.observe(container);
    }

    // Fullscreen change
    const onFullscreen = () => {
      setTimeout(updateCanvasSize, 100);
      setTimeout(updateCanvasSize, 300);
    };
    document.addEventListener("fullscreenchange", onFullscreen);
    document.addEventListener("webkitfullscreenchange", onFullscreen);
    
    return () => {
      window.removeEventListener("resize", updateCanvasSize);
      document.removeEventListener("fullscreenchange", onFullscreen);
      document.removeEventListener("webkitfullscreenchange", onFullscreen);
      resizeObserver?.disconnect();
    };
  }, [updateCanvasSize]);

  // Fullscreen the container (video + canvas together)
  const toggleFullscreen = () => {
    const container = containerRef.current;
    if (!container) return;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      container.requestFullscreen().catch(() => {});
    }
  };

  // Point-in-polygon check (ray casting)
  const pointInPolygon = (px: number, py: number, vertices: number[][]): boolean => {
    let inside = false;
    for (let i = 0, j = vertices.length - 1; i < vertices.length; j = i++) {
      const xi = vertices[i][0], yi = vertices[i][1];
      const xj = vertices[j][0], yj = vertices[j][1];
      if ((yi > py) !== (yj > py) && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) {
        inside = !inside;
      }
    }
    return inside;
  };

  // Get current frame detections based on video time
  const getCurrentDetections = useCallback((): FrameDetection | null => {
    if (!videoRef.current || frameData.length === 0) return null;
    const currentTime = videoRef.current.currentTime;
    // Find closest frame by timestamp
    let closest = frameData[0];
    let minDiff = Math.abs(currentTime - closest.timestamp_sec);
    for (const f of frameData) {
      const diff = Math.abs(currentTime - f.timestamp_sec);
      if (diff < minDiff) {
        minDiff = diff;
        closest = f;
      }
      if (f.timestamp_sec > currentTime + 0.5) break; // early exit
    }
    return closest;
  }, [frameData]);

  // Check zone violations
  const checkViolations = useCallback((detection: FrameDetection | null) => {
    if (!detection || allZones.length === 0) return;
    const now = Date.now();
    const newViolations: string[] = [];

    for (const zone of allZones) {
      if (zone.vertices.length < 3) continue;

      // Check persons
      for (const person of detection.persons) {
        const [x1, y1, x2, y2] = person.bbox;
        const video = videoRef.current;
        if (!video) continue;
        const vw = video.videoWidth || 1;
        const vh = video.videoHeight || 1;
        // Normalize bbox center to [0-1]
        const cx = ((x1 + x2) / 2) / vw;
        const cy = ((y1 + y2) / 2) / vh;

        if (pointInPolygon(cx, cy, zone.vertices)) {
          const key = `${zone.id}_person`;
          const lastAlert = alertCooldownRef.current[key] || 0;
          if (now - lastAlert > 3000) { // 3s cooldown per zone
            alertCooldownRef.current[key] = now;
            const msg = `⚠️ Person detected in zone "${zone.name}" (${zone.risk_level})`;
            newViolations.push(msg);
            onAlert?.(msg);
          }
        }
      }

      // Check vehicles
      for (const vehicle of detection.vehicles || []) {
        const [x1, y1, x2, y2] = vehicle.bbox;
        const video = videoRef.current;
        if (!video) continue;
        const vw = video.videoWidth || 1;
        const vh = video.videoHeight || 1;
        const cx = ((x1 + x2) / 2) / vw;
        const cy = ((y1 + y2) / 2) / vh;

        if (pointInPolygon(cx, cy, zone.vertices)) {
          const key = `${zone.id}_vehicle`;
          const lastAlert = alertCooldownRef.current[key] || 0;
          if (now - lastAlert > 3000) {
            alertCooldownRef.current[key] = now;
            const msg = `⚠️ ${vehicle.class_name} in zone "${zone.name}"`;
            newViolations.push(msg);
            onAlert?.(msg);
          }
        }
      }

      // Check env hazards
      for (const env of detection.env || []) {
        const [x1, y1, x2, y2] = env.bbox;
        const video = videoRef.current;
        if (!video) continue;
        const vw = video.videoWidth || 1;
        const vh = video.videoHeight || 1;
        const cx = ((x1 + x2) / 2) / vw;
        const cy = ((y1 + y2) / 2) / vh;

        if (pointInPolygon(cx, cy, zone.vertices)) {
          const key = `${zone.id}_${env.class_name}`;
          const lastAlert = alertCooldownRef.current[key] || 0;
          if (now - lastAlert > 5000) {
            alertCooldownRef.current[key] = now;
            const msg = `🔥 ${env.class_name} detected in zone "${zone.name}"`;
            newViolations.push(msg);
            onAlert?.(msg);
          }
        }
      }
    }

    if (newViolations.length > 0) {
      setViolations(prev => [...newViolations, ...prev].slice(0, 20));
      // Send first violation to backend for WhatsApp notification
      const firstMsg = newViolations[0];
      const zoneName = firstMsg.match(/"([^"]+)"/)?.[1] || "Video Sim Zone";
      fetch(`${API_URL}/alerts/sim`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          zone_name: zoneName,
          risk_level: "high",
          violation_type: "zone_violation",
          confidence: 0.9,
          source: "video_simulation",
        }),
      }).catch(() => {});
    }
  }, [allZones, onAlert]);

  // Animation loop: draw overlay on canvas synced with video
  useEffect(() => {
    let animId: number;

    const draw = () => {
      const canvas = canvasRef.current;
      const video = videoRef.current;
      if (!canvas || !video) {
        animId = requestAnimationFrame(draw);
        return;
      }

      const ctx = canvas.getContext("2d");
      if (!ctx) { animId = requestAnimationFrame(draw); return; }

      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);

      // Draw zones
      for (const zone of allZones) {
        if (zone.vertices.length < 3) continue;
        const pts = zone.vertices.map(([x, y]) => [x * w, y * h]);
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        pts.slice(1).forEach(([x, y]) => ctx.lineTo(x, y));
        ctx.closePath();

        const isHigh = zone.risk_level === "high";
        ctx.fillStyle = isHigh ? "rgba(239, 68, 68, 0.15)" : "rgba(245, 158, 11, 0.15)";
        ctx.fill();
        ctx.strokeStyle = isHigh ? "#ef4444" : "#f59e0b";
        ctx.lineWidth = 2;
        ctx.stroke();

        // Zone label
        ctx.fillStyle = "rgba(0,0,0,0.7)";
        ctx.fillRect(pts[0][0], pts[0][1] - 20, ctx.measureText(zone.name).width + 12, 18);
        ctx.fillStyle = isHigh ? "#ef4444" : "#f59e0b";
        ctx.font = "bold 11px Inter, sans-serif";
        ctx.fillText(zone.name, pts[0][0] + 4, pts[0][1] - 6);
      }

      // Draw current drawing polygon
      if (currentVertices.length > 0) {
        const pts = currentVertices.map(([x, y]) => [x * w, y * h]);
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        pts.slice(1).forEach(([x, y]) => ctx.lineTo(x, y));
        if (mousePos) ctx.lineTo(mousePos.x, mousePos.y);
        ctx.strokeStyle = "#22d3ee";
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        ctx.stroke();
        ctx.setLineDash([]);

        pts.forEach(([x, y]) => {
          ctx.beginPath();
          ctx.arc(x, y, 5, 0, Math.PI * 2);
          ctx.fillStyle = "#22d3ee";
          ctx.fill();
          ctx.strokeStyle = "#fff";
          ctx.lineWidth = 1.5;
          ctx.stroke();
        });

        ctx.fillStyle = "rgba(0,0,0,0.75)";
        ctx.fillRect(pts[0][0] - 2, pts[0][1] - 24, 180, 20);
        ctx.fillStyle = "#22d3ee";
        ctx.font = "12px Inter, sans-serif";
        ctx.fillText(`${currentVertices.length} pts (dbl-click to close)`, pts[0][0] + 4, pts[0][1] - 9);
      }

      // Draw detection bboxes if enabled and video is playing
      if (showDetections && !video.paused) {
        const detection = getCurrentDetections();
        if (detection) {
          checkViolations(detection);

          const vw = video.videoWidth || 1;
          const vh = video.videoHeight || 1;
          const scaleX = w / vw;
          const scaleY = h / vh;

          // Draw person bboxes
          for (const person of detection.persons) {
            const [x1, y1, x2, y2] = person.bbox;
            const sx = x1 * scaleX, sy = y1 * scaleY;
            const sw = (x2 - x1) * scaleX, sh = (y2 - y1) * scaleY;

            const hasViolation = person.ppe_violations && person.ppe_violations.length > 0;
            ctx.strokeStyle = hasViolation ? "#ef4444" : "#22c55e";
            ctx.lineWidth = 2;
            ctx.strokeRect(sx, sy, sw, sh);

            const label = `Person ${Math.round(person.confidence * 100)}%`;
            ctx.fillStyle = "rgba(0,0,0,0.7)";
            ctx.fillRect(sx, sy - 16, ctx.measureText(label).width + 8, 16);
            ctx.fillStyle = hasViolation ? "#ef4444" : "#22c55e";
            ctx.font = "11px Inter, sans-serif";
            ctx.fillText(label, sx + 4, sy - 4);
          }

          // Draw env hazards
          for (const env of detection.env || []) {
            const [x1, y1, x2, y2] = env.bbox;
            const sx = x1 * scaleX, sy = y1 * scaleY;
            const sw = (x2 - x1) * scaleX, sh = (y2 - y1) * scaleY;

            ctx.strokeStyle = "#f97316";
            ctx.lineWidth = 2;
            ctx.strokeRect(sx, sy, sw, sh);

            const label = `${env.class_name} ${Math.round(env.confidence * 100)}%`;
            ctx.fillStyle = "rgba(0,0,0,0.7)";
            ctx.fillRect(sx, sy - 16, ctx.measureText(label).width + 8, 16);
            ctx.fillStyle = "#f97316";
            ctx.font = "11px Inter, sans-serif";
            ctx.fillText(label, sx + 4, sy - 4);
          }

          // Draw vehicles
          for (const v of detection.vehicles || []) {
            const [x1, y1, x2, y2] = v.bbox;
            const sx = x1 * scaleX, sy = y1 * scaleY;
            const sw = (x2 - x1) * scaleX, sh = (y2 - y1) * scaleY;

            ctx.strokeStyle = "#3b82f6";
            ctx.lineWidth = 2;
            ctx.strokeRect(sx, sy, sw, sh);

            const label = `${v.class_name} ${Math.round(v.confidence * 100)}%`;
            ctx.fillStyle = "rgba(0,0,0,0.7)";
            ctx.fillRect(sx, sy - 16, ctx.measureText(label).width + 8, 16);
            ctx.fillStyle = "#3b82f6";
            ctx.font = "11px Inter, sans-serif";
            ctx.fillText(label, sx + 4, sy - 4);
          }
        }
      }

      animId = requestAnimationFrame(draw);
    };

    animId = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animId);
  }, [allZones, currentVertices, mousePos, showDetections, getCurrentDetections, checkViolations]);

  // Canvas click handlers for polygon drawing
  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawingMode) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setCurrentVertices(prev => [...prev, [x, y]]);
  };

  const handleCanvasDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawingMode || currentVertices.length < 3) return;
    e.preventDefault();
    const newZone: SimZone = {
      id: `sim_${Date.now()}`,
      name: `Zone ${zones.length + 1}`,
      vertices: currentVertices,
      color: "#ef4444",
      risk_level: "high",
    };
    setZones(prev => [...prev, newZone]);
    setCurrentVertices([]);
    setDrawingMode(false);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawingMode) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    setMousePos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-5 h-5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin mr-3" />
        <span className="text-sm text-[var(--text-muted)]">Loading detection data...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-red-400 mb-2">Failed to load: {error}</p>
        <p className="text-xs text-[var(--text-faint)]">Make sure the video has been fully processed.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Video Player + Canvas Overlay */}
      <div ref={containerRef} className="relative rounded-xl overflow-hidden border border-[var(--border)] bg-black group fullscreen:bg-black fullscreen:rounded-none">
        <video
          ref={videoRef}
          src={`${API_URL}/video/annotated/${jobId}`}
          className="w-full h-full object-contain bg-black"
          style={{ aspectRatio: "16/9" }}
          controls
          controlsList="nofullscreen"
          onLoadedMetadata={updateCanvasSize}
          onResize={updateCanvasSize}
          onPlay={updateCanvasSize}
          crossOrigin="anonymous"
        />
        <canvas
          ref={canvasRef}
          className={`absolute top-0 left-0 w-full h-full ${drawingMode ? "cursor-crosshair" : "pointer-events-none"}`}
          onClick={handleCanvasClick}
          onDoubleClick={handleCanvasDoubleClick}
          onMouseMove={handleMouseMove}
        />
        {/* Custom fullscreen button (fullscreens container so canvas stays visible) */}
        <button
          onClick={toggleFullscreen}
          className="absolute top-2 right-2 w-8 h-8 rounded-lg bg-black/60 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity hover:bg-black/80 z-10"
          title="Fullscreen (with zones)"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
          </svg>
        </button>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => { setDrawingMode(!drawingMode); setCurrentVertices([]); }}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            drawingMode
              ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"
              : "bg-[var(--bg-input)] text-[var(--text-muted)] border border-[var(--border)] hover:border-cyan-500/30 hover:text-cyan-400"
          }`}
        >
          {drawingMode ? "✕ Cancel Drawing" : "✏️ Draw Zone"}
        </button>

        <button
          onClick={() => setShowDetections(!showDetections)}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
            showDetections
              ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
              : "bg-[var(--bg-input)] text-[var(--text-muted)] border border-[var(--border)]"
          }`}
        >
          {showDetections ? "👁 Detections ON" : "👁‍🗨 Detections OFF"}
        </button>

        {dbZones.length > 0 && (
          <button
            onClick={() => setShowDbZones(!showDbZones)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              showDbZones
                ? "bg-purple-500/20 text-purple-400 border border-purple-500/30"
                : "bg-[var(--bg-input)] text-[var(--text-muted)] border border-[var(--border)]"
            }`}
          >
            {showDbZones ? `🔲 DB Zones (${dbZones.length})` : `🔲 DB Zones OFF`}
          </button>
        )}

        {zones.length > 0 && (
          <button
            onClick={() => { setZones([]); setViolations([]); }}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-all"
          >
            🗑 Clear Custom Zones
          </button>
        )}
      </div>

      {/* Zone List */}
      {allZones.length > 0 && (
        <div className="surface-card p-4">
          <h4 className="text-xs font-semibold text-[var(--text-muted)] uppercase mb-2">Active Zones ({allZones.length})</h4>
          <div className="space-y-1.5">
            {showDbZones && dbZones.map((zone) => (
              <div key={zone.id} className="flex items-center justify-between px-3 py-2 rounded-lg bg-[var(--bg-input)] border border-[var(--border)]">
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${zone.risk_level === "high" ? "bg-red-500" : "bg-amber-500"}`} />
                  <span className="text-sm text-[var(--text-main)]">{zone.name}</span>
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-500/15 text-purple-400">DB</span>
                </div>
                <span className="text-[10px] text-[var(--text-faint)]">{zone.risk_level}</span>
              </div>
            ))}
            {zones.map((zone, idx) => (
              <div key={zone.id} className="flex items-center justify-between px-3 py-2 rounded-lg bg-[var(--bg-input)] border border-[var(--border)]">
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${zone.risk_level === "high" ? "bg-red-500" : "bg-amber-500"}`} />
                  <input
                    type="text"
                    value={zone.name}
                    onChange={(e) => setZones(prev => prev.map((z, i) => i === idx ? { ...z, name: e.target.value } : z))}
                    className="bg-transparent text-sm text-[var(--text-main)] border-none outline-none w-32"
                  />
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-cyan-500/15 text-cyan-400">Custom</span>
                </div>
                <div className="flex items-center gap-2">
                  <select
                    value={zone.risk_level}
                    onChange={(e) => setZones(prev => prev.map((z, i) => i === idx ? { ...z, risk_level: e.target.value } : z))}
                    className="text-[10px] bg-[var(--bg-card)] border border-[var(--border)] rounded px-1.5 py-0.5 text-[var(--text-muted)]"
                  >
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                  <button
                    onClick={() => setZones(prev => prev.filter((_, i) => i !== idx))}
                    className="text-red-400 text-xs hover:text-red-300"
                  >✕</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Violation Alerts */}
      {violations.length > 0 && (
        <div className="surface-card p-4 border-l-4 border-l-red-500">
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold text-red-400 uppercase">Zone Violations</h4>
            <button onClick={() => setViolations([])} className="text-[10px] text-[var(--text-faint)] hover:text-[var(--text-muted)]">Clear</button>
          </div>
          <div className="space-y-1 max-h-32 overflow-y-auto">
            {violations.map((v, i) => (
              <p key={i} className="text-xs text-[var(--text-muted)]">{v}</p>
            ))}
          </div>
        </div>
      )}

      {/* Info */}
      <div className="flex items-center gap-4 text-[10px] text-[var(--text-faint)]">
        <span>📹 {filename}</span>
        <span>🎞 {frameData.length} frames analyzed</span>
        <span>⚡ {fps} FPS</span>
        {allZones.length > 0 && <span>🔲 {allZones.length} zones active</span>}
      </div>
    </div>
  );
}
