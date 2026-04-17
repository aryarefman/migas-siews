"use client";

import { useEffect, useState } from "react";

export default function LoadingScreen({ message = "INITIALIZING SAFETY PROTOCOLS" }: { message?: string }) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setProgress((prev) => (prev < 100 ? prev + 5 : 100));
    }, 25);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="fixed inset-0 z-[100] bg-[#050810] flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-xs space-y-8">
        {/* Logo */}
        <div className="flex flex-col items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center shadow-xl shadow-amber-500/20 animate-pulse">
            <span className="text-white font-extrabold text-2xl tracking-tight">S+</span>
          </div>
          <div className="text-center">
            <h2 className="text-lg font-extrabold text-white tracking-[0.3em] mb-2">SIEWS<span className="text-amber-400">+</span></h2>
            <div className="h-px w-full bg-gradient-to-r from-transparent via-[#1c2a42] to-transparent" />
          </div>
        </div>

        {/* Progress Bar */}
        <div className="space-y-3">
          <div className="flex justify-between items-end">
            <span className="text-[9px] font-bold text-amber-400 uppercase tracking-[0.15em] animate-pulse">{message}</span>
            <span className="text-[10px] font-bold text-white font-mono">{progress}%</span>
          </div>

          <div className="h-1 w-full bg-[#0c1220] overflow-hidden rounded-full border border-[#162033]">
            <div
              className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full transition-all duration-300 ease-out relative"
              style={{ width: `${progress}%` }}
            >
              <div className="absolute top-0 right-0 w-8 h-full bg-white/30 blur-sm rounded-full" />
            </div>
          </div>

          {/* Sub-status */}
          <div className="flex gap-2 opacity-30">
            <div className="text-[8px] font-semibold text-industrial-500 border border-[#162033] px-1.5 py-0.5 rounded">YOLOv8n</div>
            <div className="text-[8px] font-semibold text-industrial-500 border border-[#162033] px-1.5 py-0.5 rounded">RTSP</div>
            <div className="text-[8px] font-semibold text-industrial-500 border border-[#162033] px-1.5 py-0.5 rounded">SQLite</div>
            <div className="text-[8px] font-semibold text-industrial-500 border border-[#162033] px-1.5 py-0.5 rounded">EasyOCR</div>
          </div>
        </div>
      </div>

      {/* Background Grid */}
      <div className="absolute inset-0 pointer-events-none opacity-[0.02] overflow-hidden">
        <div className="absolute inset-0" style={{
          backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)',
          backgroundSize: '32px 32px'
        }} />
      </div>
    </div>
  );
}
