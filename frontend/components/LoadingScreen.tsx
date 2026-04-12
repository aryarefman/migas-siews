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
    <div className="fixed inset-0 z-[100] bg-industrial-950 flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-xs space-y-8">
        {/* Logo Siluet */}
        <div className="flex flex-col items-center gap-4 animate-pulse">
          <div className="w-16 h-16 bg-amber-500 flex items-center justify-center">
            <span className="text-industrial-950 font-black text-3xl">S+</span>
          </div>
          <div className="text-center">
            <h2 className="text-lg font-black text-white tracking-[0.4em] mb-1">SIEWS+</h2>
            <div className="h-[1px] w-full bg-industrial-800" />
          </div>
        </div>

        {/* Custom Progress Bar */}
        <div className="space-y-3">
          <div className="flex justify-between items-end">
            <span className="text-[10px] font-black text-amber-500 uppercase tracking-widest animate-pulse">
              {message}
            </span>
            <span className="text-[10px] font-black text-white font-mono">{progress}%</span>
          </div>
          
          <div className="h-1 w-full bg-industrial-900 overflow-hidden relative border border-industrial-800">
            {/* Scanline effect wrapper */}
            <div 
              className="h-full bg-amber-500 transition-all duration-300 ease-out relative"
              style={{ width: `${progress}%` }}
            >
              <div className="absolute top-0 right-0 w-8 h-full bg-white/30 blur-sm" />
            </div>
          </div>
          
          {/* Sub-status tags */}
          <div className="flex gap-2 opacity-40">
            <div className="text-[8px] font-bold text-industrial-500 border border-industrial-800 px-1 py-0.5">YOLO_V8n</div>
            <div className="text-[8px] font-bold text-industrial-500 border border-industrial-800 px-1 py-0.5">RTSP_READY</div>
            <div className="text-[8px] font-bold text-industrial-500 border border-industrial-800 px-1 py-0.5">SQLITE_DB</div>
          </div>
        </div>
      </div>

      {/* Background Grid Decoration */}
      <div className="absolute inset-0 pointer-events-none opacity-[0.03] overflow-hidden">
        <div className="absolute inset-0" style={{ 
          backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)',
          backgroundSize: '40px 40px' 
        }} />
      </div>
    </div>
  );
}
