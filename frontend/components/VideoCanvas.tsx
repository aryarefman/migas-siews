"use client";

import { useEffect, useRef, useState, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ZoneData {
  id: number;
  name: string;
  vertices: number[][];
  color: string;
  active: boolean;
  risk_level: string;
}

interface VideoCanvasProps {
  zones: ZoneData[];
  drawingMode: boolean;
  onZoneCreated: (vertices: number[][]) => void;
  alertFlash: boolean;
}

export default function VideoCanvas({
  zones,
  drawingMode,
  onZoneCreated,
  alertFlash,
}: VideoCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [currentVertices, setCurrentVertices] = useState<number[][]>([]);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);
  const [cameraOnline, setCameraOnline] = useState(true);

  // Handle canvas resize to match the image
  const updateCanvasSize = useCallback(() => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas) return;

    const rect = img.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
  }, []);

  useEffect(() => {
    updateCanvasSize();
    window.addEventListener("resize", updateCanvasSize);
    return () => window.removeEventListener("resize", updateCanvasSize);
  }, [updateCanvasSize]);

  // Draw zones on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const w = canvas.width;
    const h = canvas.height;

    // Draw active zones (the backend already draws them on the MJPEG frame,
    // but we also draw on canvas for interactive editing)
    // We only draw on canvas when in drawing mode to avoid doubling
    if (drawingMode) {
      zones.forEach((zone) => {
        if (!zone.active) return;
        const pts = zone.vertices.map(([x, y]) => [x * w, y * h]);
        if (pts.length < 2) return;

        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        pts.slice(1).forEach(([x, y]) => ctx.lineTo(x, y));
        ctx.closePath();

        const isHigh = zone.risk_level === "high";
        ctx.fillStyle = isHigh
          ? "rgba(239, 68, 68, 0.15)"
          : "rgba(245, 158, 11, 0.15)";
        ctx.fill();
        ctx.strokeStyle = isHigh ? "#ef4444" : "#f59e0b";
        ctx.lineWidth = 2;
        ctx.stroke();
      });
    }

    // Draw current vertices being placed
    if (currentVertices.length > 0) {
      const pts = currentVertices.map(([x, y]) => [x * w, y * h]);

      // Draw lines
      ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      pts.slice(1).forEach(([x, y]) => ctx.lineTo(x, y));

      // Preview line to mouse
      if (mousePos) {
        ctx.lineTo(mousePos.x, mousePos.y);
      }

      ctx.strokeStyle = "#22d3ee";
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw vertices
      pts.forEach(([x, y]) => {
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fillStyle = "#22d3ee";
        ctx.fill();
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });

      // Vertex count label
      ctx.fillStyle = "rgba(0,0,0,0.7)";
      ctx.fillRect(pts[0][0] - 2, pts[0][1] - 22, 120, 18);
      ctx.fillStyle = "#22d3ee";
      ctx.font = "12px Inter, sans-serif";
      ctx.fillText(
        `${currentVertices.length} vertices (dbl-click to close)`,
        pts[0][0] + 2,
        pts[0][1] - 8
      );
    }

    // Flash effect on alert
    if (alertFlash) {
      ctx.strokeStyle = "rgba(239, 68, 68, 0.8)";
      ctx.lineWidth = 6;
      ctx.strokeRect(3, 3, w - 6, h - 6);

      ctx.fillStyle = "rgba(239, 68, 68, 0.15)";
      ctx.fillRect(0, 0, w, h);

      // Alert Text
      ctx.fillStyle = "#ef4444";
      ctx.font = "black 48px Inter, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("SYSTEM ALERT", w / 2, h / 2 - 20);
      ctx.font = "bold 16px Inter, sans-serif";
      ctx.fillText("INTRUSION DETECTED", w / 2, h / 2 + 20);
      ctx.textAlign = "start";
    }
  }, [zones, currentVertices, mousePos, drawingMode, alertFlash]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawingMode) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;

    setCurrentVertices((prev) => [...prev, [x, y]]);
  };

  const handleCanvasDoubleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawingMode || currentVertices.length < 3) return;
    e.preventDefault();

    onZoneCreated(currentVertices);
    setCurrentVertices([]);
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawingMode) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    setMousePos({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  };

  const handleImgError = () => {
    setCameraOnline(false);
    // Retry after 5 seconds
    setTimeout(() => {
      if (imgRef.current) {
        imgRef.current.src = `${API_URL}/stream?t=${Date.now()}`;
        setCameraOnline(true);
      }
    }, 5000);
  };

  return (
    <div
      ref={containerRef}
      className={`relative h-full w-full rounded-xl overflow-hidden border-2 transition-all duration-300 flex flex-col bg-black ${
        alertFlash
          ? "border-red-500 shadow-lg shadow-red-500/30"
          : "border-industrial-700/50"
      }`}
    >
      {/* MJPEG Stream */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        ref={imgRef}
        src={`${API_URL}/stream`}
        alt="Live Camera Feed"
        className="w-full h-full block object-contain"
        onLoad={updateCanvasSize}
        onError={handleImgError}
        style={{ background: "#000" }}
      />

      {/* Interactive Canvas Overlay */}
      <canvas
        ref={canvasRef}
        className={`absolute top-0 left-0 w-full h-full ${
          drawingMode ? "cursor-crosshair" : "pointer-events-none"
        }`}
        onClick={handleCanvasClick}
        onDoubleClick={handleCanvasDoubleClick}
        onMouseMove={handleMouseMove}
      />

      {/* Camera Offline Overlay */}
      {!cameraOnline && (
        <div className="absolute inset-0 bg-black/90 flex flex-col items-center justify-center">
          <svg className="w-12 h-12 text-red-600 mb-4" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z"/>
          </svg>
          <p className="text-[10px] text-red-500 font-black uppercase tracking-[0.3em]">CAMERA FEED OFFLINE</p>
          <p className="text-industrial-500 text-[9px] font-bold uppercase mt-2">
            Attempting to Reestablish Connection...
          </p>
          <div className="mt-6 w-6 h-6 border-2 border-red-950 border-t-red-500 rounded-full animate-spin" />
        </div>
      )}

      {/* Drawing Mode Indicator */}
      {drawingMode && (
        <div className="absolute top-3 left-3 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cyan-500/20 border border-cyan-500/40 backdrop-blur-sm">
          <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
          <span className="text-cyan-400 text-xs font-medium">
            DRAWING MODE — Click to place vertices, double-click to close
          </span>
        </div>
      )}

      {/* Live indicator */}
      <div className="absolute top-3 right-3 flex items-center gap-2 px-2.5 py-1 rounded-md bg-black/60 backdrop-blur-sm">
        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
        <span className="text-white text-xs font-medium tracking-wider">
          LIVE
        </span>
      </div>
    </div>
  );
}
