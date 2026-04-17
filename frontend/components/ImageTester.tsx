"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export default function ImageTester() {
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setAnalyzing(true);
    setResult(null);
    setError(null);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`/api/analyze`, {
        method: "POST",
        body: formData,
      });

      if (res.ok) {
        setResult(await res.json());
      } else {
        const err = await res.json();
        setError(err.detail || "Gagal menganalisa gambar. Coba lagi.");
      }
    } catch (err) {
      setError("Koneksi ke AI terputus. Pastikan backend menyala.");
      console.error(err);
    } finally {
      setAnalyzing(false);
    }
  };

  const startSimulation = async () => {
    if (!result?.image) return;
    try {
      const base64Response = await fetch(result.image);
      const blob = await base64Response.blob();
      const formData = new FormData();
      formData.append("file", blob, "simulation.jpg");
      await fetch(`${API_URL}/stream/simulate`, { method: "POST", body: formData });
      alert("SYST: Simulation Mode Active — Live monitoring switched to photo feed.");
    } catch (err) {
      console.error(err);
    }
  };

  const stopSimulation = async () => {
    try {
      await fetch(`${API_URL}/stream/reset`, { method: "POST" });
      alert("SYST: Resuming live camera monitor.");
      window.location.reload();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="p-4 border-t border-[#162033]">
      {/* Section Header */}
      <h3 className="text-[10px] font-bold text-industrial-400 uppercase tracking-[0.15em] mb-3 flex items-center gap-2">
        <div className="w-5 h-5 rounded bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
          <svg className="w-3 h-3 text-blue-400" fill="currentColor" viewBox="0 0 24 24">
            <path d="M5 21q-.825 0-1.413-.587T3 19V5q0-.825.587-1.413T5 3h14q.825 0 1.413.587T21 5v14q0 .825-.587 1.413T19 21H5zm0-2h14V5H5v14zm2-2h10l-3.5-4.5-2.5 3-1.5-2L7 17zm-2 2V5v14z"/>
          </svg>
        </div>
        AI Photo Lab
      </h3>

      <div className="space-y-3">
        {!analyzing ? (
          <label className="block w-full text-center py-4 rounded-lg border-2 border-dashed border-[#1c2a42] hover:border-amber-500/30 hover:bg-amber-500/5 transition-all cursor-pointer group">
            <input type="file" className="hidden" accept="image/*" onChange={handleUpload} />
            <svg className="w-5 h-5 text-industrial-600 group-hover:text-amber-400 mx-auto mb-2 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <p className="text-[10px] font-semibold text-industrial-500 uppercase tracking-widest group-hover:text-amber-400 transition-colors">Upload & Analyze</p>
          </label>
        ) : (
          <div className="py-5 text-center rounded-lg border border-[#1c2a42] bg-[#070d18]">
            <div className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            <p className="text-[10px] font-semibold text-amber-400 animate-pulse uppercase tracking-widest">Processing...</p>
          </div>
        )}

        {error && (
          <div className="p-3 bg-red-500/8 border border-red-500/20 rounded-lg animate-fade-in">
            <p className="text-[10px] font-semibold text-red-400 flex items-center gap-2">
              <svg className="w-3.5 h-3.5 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/></svg>
              {error}
            </p>
          </div>
        )}

        {result && (
          <div className="animate-fade-in space-y-3">
            {/* Action Buttons */}
            <div className="flex gap-2">
              <button
                onClick={startSimulation}
                className="flex-1 py-2 rounded-lg bg-emerald-500/15 border border-emerald-500/25 text-emerald-400 text-[10px] font-bold uppercase tracking-widest hover:bg-emerald-500/25 transition-all flex items-center justify-center gap-2"
              >
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                Inject
              </button>
              <button
                onClick={stopSimulation}
                className="px-4 py-2 rounded-lg bg-[#0f1729] border border-[#1c2a42] text-industrial-400 text-[10px] font-bold uppercase tracking-widest hover:text-white hover:border-[#243b5c] transition-all"
              >
                Stop
              </button>
            </div>

            {/* Result Image */}
            <div className="relative aspect-video rounded-lg overflow-hidden border border-[#1c2a42]">
              <img src={result.image} alt="Annotated Result" className="w-full h-full object-contain bg-black" />
              <button
                onClick={() => setResult(null)}
                className="absolute top-2 right-2 p-1.5 rounded-md bg-black/70 text-industrial-400 hover:text-red-400 transition-colors"
              >
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
              </button>
            </div>

            {/* Detection List */}
            <div className="space-y-1.5">
              {result.detections.map((d: any, i: number) => (
                <div key={i} className="px-3 py-2 rounded-lg bg-[#070d18] border-l-2 border-blue-500/60 flex justify-between items-center">
                  <div>
                    <p className="text-[10px] font-bold text-white uppercase">{d.face_name || "Unknown"}</p>
                    <p className="text-[9px] text-industrial-500 font-mono">ID: {d.ocr_code || "N/A"}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-[11px] font-bold text-emerald-400">{(d.confidence * 100).toFixed(0)}%</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
