"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface AnalyzeResult {
  image: string;
  summary?: Record<string, number>;
  detections?: any[];
  hazards?: any[];
  vehicles?: any[];
  road?: any[];
  ocr?: any[];
}

export default function ImageTester() {
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) { setError("File harus gambar"); return; }
    if (file.size > 10 * 1024 * 1024) { setError("Max 10MB"); return; }

    setAnalyzing(true);
    setResult(null);
    setError(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      // Run detection + OCR in parallel
      const [detectRes, ocrRes] = await Promise.all([
        fetch(`${API_URL}/ai/analyze-image`, { method: "POST", body: formData }),
        fetch(`${API_URL}/ocr/test`, { method: "POST", body: (() => { const f = new FormData(); f.append("file", file); return f; })() }),
      ]);

      const detectData = detectRes.ok ? await detectRes.json() : {};
      const ocrData = ocrRes.ok ? await ocrRes.json() : { results: [] };

      setResult({
        image: detectData.image || "",
        summary: detectData.summary,
        detections: detectData.detections || [],
        hazards: detectData.hazards || [],
        vehicles: detectData.vehicles || [],
        road: detectData.road || [],
        ocr: ocrData.results || [],
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error");
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Upload */}
      {!analyzing ? (
        <label className="block w-full text-center py-5 rounded-lg border-2 border-dashed border-[var(--border)] hover:border-[var(--accent)]/30 cursor-pointer">
          <input type="file" className="hidden" accept="image/*" onChange={handleUpload} />
          <span className="text-xs font-medium text-[var(--text-muted)]">+ UPLOAD & ANALYZE</span>
        </label>
      ) : (
        <div className="py-5 text-center rounded-lg border border-[var(--border)]">
          <div className="w-5 h-5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin mx-auto mb-2" />
          <p className="text-xs text-[var(--accent-light)]">Processing...</p>
        </div>
      )}

      {error && <p className="text-xs text-red-400 p-3 bg-red-500/10 rounded-lg">{error}</p>}

      {result && (
        <div className="space-y-4 animate-fade-in">
          {/* Annotated Image */}
          {result.image && (
            <div className="relative rounded-lg overflow-hidden border border-[var(--border)]">
              <img src={result.image} alt="Result" className="w-full object-contain bg-black" />
              <button onClick={() => setResult(null)} className="absolute top-2 right-2 w-6 h-6 rounded-full bg-black/70 text-white text-xs flex items-center justify-center">×</button>
            </div>
          )}

          {/* Summary */}
          {result.summary && (
            <div className="grid grid-cols-3 gap-2 text-center">
              {Object.entries(result.summary).map(([k, v]) => (
                <div key={k} className="p-2 rounded-lg bg-[var(--bg-input)] border border-[var(--border)]">
                  <p className="text-lg font-bold text-[var(--text-main)]">{v}</p>
                  <p className="text-[9px] text-[var(--text-faint)] uppercase">{k.replace(/_/g, " ")}</p>
                </div>
              ))}
            </div>
          )}

          {/* Persons */}
          {result.detections && result.detections.length > 0 && (
            <div>
              <h4 className="text-[10px] font-bold text-[var(--text-muted)] uppercase mb-2">Persons ({result.detections.length})</h4>
              {result.detections.map((d: any, i: number) => (
                <div key={i} className="px-3 py-2 mb-1 rounded bg-[var(--bg-input)] border-l-2 border-emerald-500/60 flex justify-between">
                  <span className="text-xs text-[var(--text-main)]">{d.face_name || "Unknown"} {d.ocr_code ? `[${d.ocr_code}]` : ""}</span>
                  <span className="text-xs text-emerald-400">{(d.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}

          {/* Hazards */}
          {result.hazards && result.hazards.length > 0 && (
            <div>
              <h4 className="text-[10px] font-bold text-[var(--text-muted)] uppercase mb-2">Hazards ({result.hazards.length})</h4>
              {result.hazards.map((h: any, i: number) => (
                <div key={i} className="px-3 py-2 mb-1 rounded bg-[var(--bg-input)] border-l-2 border-red-500/60 flex justify-between">
                  <span className="text-xs text-[var(--text-main)]">{h.label || h.class_name}</span>
                  <span className="text-xs text-red-400">{(h.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}

          {/* Vehicles */}
          {result.vehicles && result.vehicles.length > 0 && (
            <div>
              <h4 className="text-[10px] font-bold text-[var(--text-muted)] uppercase mb-2">Vehicles ({result.vehicles.length})</h4>
              {result.vehicles.map((v: any, i: number) => (
                <div key={i} className="px-3 py-2 mb-1 rounded bg-[var(--bg-input)] border-l-2 border-purple-500/60 flex justify-between">
                  <span className="text-xs text-[var(--text-main)]">{v.class_name || v.label}</span>
                  <span className="text-xs text-purple-400">{(v.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}

          {/* Road */}
          {result.road && result.road.length > 0 && (
            <div>
              <h4 className="text-[10px] font-bold text-[var(--text-muted)] uppercase mb-2">Road Damage ({result.road.length})</h4>
              {result.road.map((r: any, i: number) => (
                <div key={i} className="px-3 py-2 mb-1 rounded bg-[var(--bg-input)] border-l-2 border-amber-500/60 flex justify-between">
                  <span className="text-xs text-[var(--text-main)]">{r.class_name || r.label}</span>
                  <span className="text-xs text-amber-400">{(r.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}

          {/* OCR */}
          {result.ocr && result.ocr.length > 0 && (
            <div>
              <h4 className="text-[10px] font-bold text-[var(--text-muted)] uppercase mb-2">OCR Text ({result.ocr.length})</h4>
              {result.ocr.map((o: any, i: number) => (
                <div key={i} className="px-3 py-2 mb-1 rounded bg-[var(--bg-input)] border-l-2 border-cyan-500/60 flex justify-between">
                  <span className="text-xs text-[var(--text-main)] font-mono">{o.text}</span>
                  <span className="text-xs text-cyan-400">{(o.confidence * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
