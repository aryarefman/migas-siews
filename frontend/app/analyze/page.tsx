"use client";

import { useState, useCallback, useRef } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Detection {
  label: string;
  confidence: number;
  bbox: number[];
}

interface Person {
  bbox: number[];
  confidence: number;
  violations: string[];
  ppe_status: Record<string, number>;
}

interface AnalysisResult {
  annotated_image: string;
  image_size: { width: number; height: number };
  detections: {
    persons: Person[];
    env: Detection[];
    total_persons: number;
    total_env: number;
    violations_found: boolean;
  };
}

export default function AnalyzePage() {
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const analyze = useCallback(async (file: File) => {
    setError(null);
    setResult(null);
    setLoading(true);

    // Show original preview immediately
    const reader = new FileReader();
    reader.onload = (e) => setPreview(e.target?.result as string);
    reader.readAsDataURL(file);

    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_URL}/analyze/image`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Analisis gagal");
      }
      const data: AnalysisResult = await res.json();
      setResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Terjadi kesalahan.");
    } finally {
      setLoading(false);
    }
  }, []);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) analyze(file);
  };

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) analyze(file);
    },
    [analyze]
  );

  const reset = () => {
    setPreview(null);
    setResult(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const violations = result?.detections.persons.flatMap((p) => p.violations) ?? [];
  const envDetections = result?.detections.env ?? [];
  const roadDetections = (result?.detections as any)?.road ?? [];

  return (
    <div className="min-h-screen bg-[#0a0e17] text-slate-200 p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-black text-amber-400 tracking-tight">
            🔍 Analisis Foto
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Upload foto untuk dianalisis oleh model aktif:{" "}
            <span className="text-green-400 font-semibold">S1 Person</span> +{" "}
            <span className="text-cyan-400 font-semibold">S3 Open Hole</span>
          </p>
        </div>

        {/* Upload Area */}
        {!preview && (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => inputRef.current?.click()}
            className={`
              border-2 border-dashed rounded-xl p-16 text-center cursor-pointer transition-all
              ${dragging
                ? "border-amber-400 bg-amber-400/10"
                : "border-slate-600 hover:border-amber-500 hover:bg-slate-800/50"}
            `}
          >
            <div className="text-5xl mb-4">📷</div>
            <p className="text-lg font-semibold text-slate-300">
              Drag & drop foto di sini
            </p>
            <p className="text-slate-500 text-sm mt-1">
              atau klik untuk browse — JPG, PNG, BMP, WEBP
            </p>
            <input
              ref={inputRef}
              type="file"
              accept="image/jpeg,image/png,image/bmp,image/webp"
              className="hidden"
              onChange={onFileChange}
            />
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center gap-3 py-8">
            <div className="w-6 h-6 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
            <span className="text-amber-400 font-semibold">Menganalisis gambar...</span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-red-900/40 border border-red-500/50 rounded-lg p-4 text-red-300">
            ❌ {error}
          </div>
        )}

        {/* Results */}
        {result && !loading && (
          <div className="space-y-6">
            {/* Status Banner */}
            <div className={`rounded-xl p-4 border flex items-center gap-3 ${result.detections.violations_found
              ? "bg-red-900/40 border-red-500/50"
              : "bg-green-900/40 border-green-500/50"
              }`}>
              <span className="text-3xl">
                {result.detections.violations_found ? "🚨" : "✅"}
              </span>
              <div>
                <p className="font-black text-lg">
                  {result.detections.violations_found
                    ? "Pelanggaran Ditemukan!"
                    : "Tidak Ada Pelanggaran"}
                </p>
                <p className="text-sm text-slate-400">
                  {result.detections.total_persons} orang terdeteksi ·{" "}
                  {result.detections.total_env} objek konstruksi ·{" "}
                  {(result.detections as any).total_road ?? 0} kerusakan jalan ·{" "}
                  {result.image_size.width}×{result.image_size.height}px
                </p>
              </div>
            </div>

            {/* Images Side by Side */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">
                  Original
                </p>
                <img
                  src={preview!}
                  alt="original"
                  className="w-full rounded-lg border border-slate-700"
                />
              </div>
              <div className="space-y-2">
                <p className="text-xs font-bold text-amber-400 uppercase tracking-widest">
                  Hasil Deteksi
                </p>
                <img
                  src={result.annotated_image}
                  alt="annotated"
                  className="w-full rounded-lg border border-amber-500/40"
                />
              </div>
            </div>

            {/* Detection Details */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Persons */}
              <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4 space-y-3">
                <h3 className="font-black text-sm uppercase tracking-widest text-green-400">
                  👤 Orang Terdeteksi ({result.detections.total_persons})
                </h3>
                {result.detections.persons.length === 0 ? (
                  <p className="text-slate-500 text-sm">Tidak ada orang</p>
                ) : (
                  result.detections.persons.map((p, i) => (
                    <div key={i} className="border border-slate-600 rounded-lg p-3 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-sm">Person #{i + 1}</span>
                        <span className="text-xs text-slate-400">
                          conf: {(p.confidence * 100).toFixed(1)}%
                        </span>
                      </div>
                      {p.violations.length > 0 && (
                        <div className="flex flex-wrap gap-1">
                          {p.violations.map((v) => (
                            <span
                              key={v}
                              className="text-xs bg-red-900/60 text-red-300 border border-red-500/40 px-2 py-0.5 rounded"
                            >
                              ⚠️ {v}
                            </span>
                          ))}
                        </div>
                      )}
                      {p.violations.length === 0 && (
                        <span className="text-xs text-green-400">✅ Tidak ada pelanggaran</span>
                      )}
                    </div>
                  ))
                )}
              </div>

              {/* Environment */}
              <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4 space-y-3">
                <h3 className="font-black text-sm uppercase tracking-widest text-cyan-400">
                  🏗️ Objek Konstruksi ({result.detections.total_env})
                </h3>
                {envDetections.length === 0 ? (
                  <p className="text-slate-500 text-sm">Tidak ada objek terdeteksi</p>
                ) : (
                  envDetections.map((d, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between border border-slate-600 rounded-lg px-3 py-2"
                    >
                      <span className="text-sm font-semibold capitalize">
                        {d.label.replace(/-/g, " ")}
                      </span>
                      <span className={`text-xs font-bold px-2 py-0.5 rounded ${d.label === "open-hole"
                        ? "bg-red-900/60 text-red-300"
                        : "bg-slate-700 text-slate-300"
                        }`}>
                        {(d.confidence * 100).toFixed(1)}%
                      </span>
                    </div>
                  ))
                )}
              </div>

              {/* Road Damage */}
              <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4 space-y-3">
                <h3 className="font-black text-sm uppercase tracking-widest text-blue-400">
                  🛣️ Kerusakan Jalan ({(result.detections as any).total_road ?? 0})
                </h3>
                {roadDetections.length === 0 ? (
                  <p className="text-slate-500 text-sm">Tidak ada kerusakan jalan terdeteksi</p>
                ) : (
                  roadDetections.map((d: any, i: number) => (
                    <div
                      key={i}
                      className="flex items-center justify-between border border-slate-600 rounded-lg px-3 py-2"
                    >
                      <span className="text-sm font-semibold capitalize">
                        {d.label.replace(/-/g, " ")}
                      </span>
                      <span className={`text-xs font-bold px-2 py-0.5 rounded ${d.label === "lubang"
                        ? "bg-blue-900/60 text-blue-300"
                        : d.label === "retak"
                          ? "bg-orange-900/60 text-orange-300"
                          : "bg-green-900/60 text-green-300"
                        }`}>
                        {(d.confidence * 100).toFixed(1)}%
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Violations Summary */}
            {violations.length > 0 && (
              <div className="bg-red-900/30 border border-red-500/40 rounded-xl p-4">
                <h3 className="font-black text-sm uppercase tracking-widest text-red-400 mb-2">
                  🚨 Ringkasan Pelanggaran
                </h3>
                <div className="flex flex-wrap gap-2">
                  {Array.from(new Set(violations)).map((v) => (
                    <span
                      key={v}
                      className="bg-red-800/60 text-red-200 border border-red-500/50 px-3 py-1 rounded-full text-sm font-semibold"
                    >
                      {v}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Upload Another */}
            <button
              onClick={reset}
              className="w-full py-3 rounded-xl border border-amber-500/50 text-amber-400 font-bold hover:bg-amber-500/10 transition-colors"
            >
              + Upload Foto Lain
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
