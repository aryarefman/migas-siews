"use client";

import { useState, useRef, useEffect, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface VideoJob {
  id: number;
  filename: string;
  status: "pending" | "processing" | "done" | "failed";
  progress: number;
  total_frames: number;
  processed_frames: number;
  created_at: string;
  completed_at: string | null;
  error_message?: string;
}

interface FrameDetection {
  frame: number;
  timestamp_sec: number;
  has_violation: boolean;
  persons: {
    bbox: number[];
    confidence: number;
    ppe_violations: string[];
    ppe: Record<string, number>;
  }[];
  env: {
    class_name: string;
    confidence: number;
    bbox: number[];
  }[];
}

interface VideoResult {
  job_id: number;
  filename: string;
  total_frames_processed: number;
  total_violation_frames: number;
  frames: FrameDetection[];
}

const STATUS_COLOR: Record<string, string> = {
  pending: "text-industrial-400",
  processing: "text-amber-400",
  done: "text-emerald-400",
  failed: "text-red-400",
};

export default function VideoAnalysisPage() {
  const [jobs, setJobs] = useState<VideoJob[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [selectedJob, setSelectedJob] = useState<VideoJob | null>(null);
  const [result, setResult] = useState<VideoResult | null>(null);
  const [loadingResult, setLoadingResult] = useState(false);
  const [filterViolations, setFilterViolations] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const fetchJobs = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/video/jobs`);
      if (res.ok) setJobs(await res.json());
    } catch { /* offline */ }
  }, []);

  useEffect(() => {
    fetchJobs();
    pollRef.current = setInterval(fetchJobs, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [fetchJobs]);

  const handleUpload = async (file: File) => {
    if (!file) return;
    const allowed = ["mp4", "avi", "mkv", "mov", "webm"];
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    if (!allowed.includes(ext)) {
      alert(`Format tidak didukung: .${ext}\nFormat yang didukung: ${allowed.join(", ")}`);
      return;
    }

    setUploading(true);
    const form = new FormData();
    form.append("file", file);

    try {
      const res = await fetch(`${API_URL}/video/upload`, { method: "POST", body: form });
      if (res.ok) {
        await fetchJobs();
      } else {
        const err = await res.json();
        alert(`Upload gagal: ${err.detail}`);
      }
    } catch {
      alert("Upload gagal. Backend tidak terhubung.");
    } finally {
      setUploading(false);
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
    e.target.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleUpload(file);
  };

  const loadResult = async (job: VideoJob) => {
    setSelectedJob(job);
    setResult(null);
    if (job.status !== "done") return;
    setLoadingResult(true);
    try {
      const res = await fetch(`${API_URL}/video/jobs/${job.id}/result`);
      if (res.ok) setResult(await res.json());
    } catch { /* offline */ }
    finally { setLoadingResult(false); }
  };

  const deleteJob = async (jobId: number) => {
    if (!confirm("Hapus job ini?")) return;
    await fetch(`${API_URL}/video/jobs/${jobId}`, { method: "DELETE" });
    if (selectedJob?.id === jobId) { setSelectedJob(null); setResult(null); }
    fetchJobs();
  };

  const exportCSV = () => {
    if (!result) return;
    const rows = ["Frame,Timestamp(s),Has Violation,Persons,PPE Violations,Fire/Smoke"];
    for (const f of result.frames) {
      const violations = f.persons.flatMap((p) => p.ppe_violations).join("|");
      const env = f.env.map((d) => d.class_name).join("|");
      rows.push(`${f.frame},${f.timestamp_sec},${f.has_violation},${f.persons.length},"${violations}","${env}"`);
    }
    const blob = new Blob([rows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${result.filename}_detections.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const displayFrames = result
    ? filterViolations
      ? result.frames.filter((f) => f.has_violation)
      : result.frames
    : [];

  return (
    <div className="min-h-screen p-4 max-w-[1920px] mx-auto">
      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <div className="w-1 h-8 bg-amber-500" />
        <div>
          <h1 className="text-sm font-black text-white uppercase tracking-[0.3em]">Video Analysis</h1>
          <p className="text-[10px] text-industrial-500 uppercase tracking-widest">
            Upload video untuk deteksi PPE · Harness · Fire/Smoke
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-[calc(100vh-120px)]">

        {/* Left: Upload + Job List */}
        <div className="lg:col-span-1 flex flex-col gap-4 overflow-hidden">

          {/* Drop Zone */}
          <div
            className={`border-2 border-dashed p-8 text-center cursor-pointer transition-all ${dragOver
                ? "border-amber-500 bg-amber-950/20"
                : "border-industrial-700 hover:border-industrial-600"
              } ${uploading ? "opacity-50 pointer-events-none" : ""}`}
            onClick={() => fileRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".mp4,.avi,.mkv,.mov,.webm"
              onChange={handleFileInput}
              className="hidden"
            />
            <div className="mb-3">
              {uploading ? (
                <div className="w-10 h-10 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto" />
              ) : (
                <svg className="w-10 h-10 text-industrial-600 mx-auto" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z" />
                </svg>
              )}
            </div>
            <p className="text-[11px] font-black text-white uppercase tracking-wider mb-1">
              {uploading ? "Uploading..." : "Drop Video File"}
            </p>
            <p className="text-[9px] text-industrial-600 uppercase">
              mp4 · avi · mkv · mov · webm
            </p>
          </div>

          {/* Job List */}
          <div className="flex-1 bg-industrial-900 border border-industrial-800 overflow-hidden flex flex-col">
            <div className="p-3 border-b border-industrial-800">
              <h2 className="text-[10px] font-black text-white uppercase tracking-widest">
                Processing Jobs ({jobs.length})
              </h2>
            </div>
            <div className="flex-1 overflow-y-auto">
              {jobs.length === 0 ? (
                <div className="py-10 text-center text-[10px] text-industrial-600 uppercase tracking-widest">
                  No jobs yet
                </div>
              ) : (
                jobs.map((job) => (
                  <div
                    key={job.id}
                    onClick={() => loadResult(job)}
                    className={`p-3 border-b border-industrial-800 cursor-pointer transition-all hover:bg-industrial-800 ${selectedJob?.id === job.id ? "bg-industrial-800 border-l-2 border-l-amber-500" : ""
                      }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-[11px] font-bold text-white truncate">{job.filename}</p>
                        <p className={`text-[9px] font-black uppercase tracking-wider ${STATUS_COLOR[job.status]}`}>
                          {job.status}
                          {job.status === "processing" && ` — ${job.progress}%`}
                        </p>
                      </div>
                      <button
                        onClick={(e) => { e.stopPropagation(); deleteJob(job.id); }}
                        className="text-industrial-600 hover:text-red-500 text-sm transition-all shrink-0"
                      >
                        ✕
                      </button>
                    </div>
                    {job.status === "processing" && (
                      <div className="mt-2 h-1 bg-industrial-900 overflow-hidden">
                        <div
                          className="h-full bg-amber-500 transition-all duration-500"
                          style={{ width: `${job.progress}%` }}
                        />
                      </div>
                    )}
                    {job.status === "done" && (
                      <p className="text-[9px] text-industrial-500 mt-1">
                        {job.processed_frames.toLocaleString()} frames processed
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Right: Result Viewer */}
        <div className="lg:col-span-2 bg-industrial-900 border border-industrial-800 flex flex-col overflow-hidden">
          {!selectedJob ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <svg className="w-16 h-16 text-industrial-800 mx-auto mb-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M18 4l2 4h-3l-2-4h-2l2 4h-3l-2-4H8l2 4H7L5 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V4h-4z" />
                </svg>
                <p className="text-[10px] text-industrial-600 uppercase tracking-widest">
                  Pilih job untuk melihat hasil
                </p>
              </div>
            </div>
          ) : selectedJob.status === "pending" || selectedJob.status === "processing" ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-4">
              <div className="w-16 h-16 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
              <div className="text-center">
                <p className="text-[11px] font-black text-amber-400 uppercase tracking-wider mb-1">
                  {selectedJob.status === "pending" ? "Menunggu..." : `Processing ${selectedJob.progress}%`}
                </p>
                <p className="text-[9px] text-industrial-500">{selectedJob.filename}</p>
              </div>
              {selectedJob.status === "processing" && (
                <div className="w-64 h-1.5 bg-industrial-800">
                  <div
                    className="h-full bg-amber-500 transition-all duration-500"
                    style={{ width: `${selectedJob.progress}%` }}
                  />
                </div>
              )}
            </div>
          ) : selectedJob.status === "failed" ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <p className="text-[11px] font-black text-red-500 uppercase tracking-wider mb-2">Processing Failed</p>
                <p className="text-[9px] text-industrial-500">{selectedJob.error_message}</p>
              </div>
            </div>
          ) : loadingResult ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : result ? (
            <>
              {/* Result Header */}
              <div className="p-4 border-b border-industrial-800 shrink-0">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div>
                    <h2 className="text-[11px] font-black text-white uppercase tracking-widest mb-2">
                      {result.filename}
                    </h2>
                    <div className="flex gap-4 flex-wrap">
                      <div className="text-center">
                        <p className="text-lg font-black text-white">{result.total_frames_processed.toLocaleString()}</p>
                        <p className="text-[9px] text-industrial-500 uppercase">Frames</p>
                      </div>
                      <div className="text-center">
                        <p className="text-lg font-black text-red-500">{result.total_violation_frames.toLocaleString()}</p>
                        <p className="text-[9px] text-industrial-500 uppercase">Violations</p>
                      </div>
                      <div className="text-center">
                        <p className="text-lg font-black text-amber-400">
                          {result.total_frames_processed > 0
                            ? ((result.total_violation_frames / result.total_frames_processed) * 100).toFixed(1)
                            : 0}%
                        </p>
                        <p className="text-[9px] text-industrial-500 uppercase">Rate</p>
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2 items-center flex-wrap">
                    <button
                      onClick={() => setFilterViolations(!filterViolations)}
                      className={`px-3 py-1.5 text-[9px] font-black uppercase tracking-wider border transition-all ${filterViolations
                          ? "bg-red-600 border-red-500 text-white"
                          : "bg-industrial-800 border-industrial-700 text-industrial-400"
                        }`}
                    >
                      {filterViolations ? "All Frames" : "Violations Only"}
                    </button>
                    <button
                      onClick={exportCSV}
                      className="px-3 py-1.5 text-[9px] font-black uppercase tracking-wider bg-industrial-800 border border-industrial-700 text-industrial-400 hover:text-white hover:bg-industrial-700 transition-all"
                    >
                      Export CSV
                    </button>
                  </div>
                </div>
              </div>

              {/* Frame List */}
              <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {displayFrames.length === 0 ? (
                  <div className="py-10 text-center text-[10px] text-industrial-600 uppercase tracking-widest">
                    {filterViolations ? "Tidak ada frame pelanggaran" : "Tidak ada deteksi"}
                  </div>
                ) : (
                  displayFrames.map((frame) => (
                    <div
                      key={frame.frame}
                      className={`p-3 border transition-all ${frame.has_violation
                          ? "border-red-800 bg-red-950/10"
                          : "border-industrial-800 bg-industrial-950/30"
                        }`}
                    >
                      <div className="flex items-start justify-between gap-3 flex-wrap">
                        <div className="flex items-center gap-3">
                          <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${frame.has_violation ? "bg-red-500" : "bg-emerald-500"
                            }`} />
                          <div>
                            <p className="text-[10px] font-black text-white">
                              Frame {frame.frame}
                              <span className="text-industrial-500 font-normal ml-2">
                                {frame.timestamp_sec}s
                              </span>
                            </p>
                            <div className="flex gap-2 mt-1 flex-wrap">
                              {frame.persons.length > 0 && (
                                <span className="text-[9px] text-industrial-400">
                                  {frame.persons.length} person{frame.persons.length > 1 ? "s" : ""}
                                </span>
                              )}
                              {frame.persons.flatMap((p) => p.ppe_violations).map((v, i) => (
                                <span key={i} className="text-[9px] font-bold text-red-400 uppercase">
                                  {v.replace("_", " ")}
                                </span>
                              ))}
                              {frame.env.map((d, i) => (
                                <span key={i} className="text-[9px] font-bold text-orange-400 uppercase">
                                  {d.class_name} {(d.confidence * 100).toFixed(0)}%
                                </span>
                              ))}
                            </div>
                          </div>
                        </div>
                        {frame.persons.map((p, pi) =>
                          Object.keys(p.ppe).length > 0 ? (
                            <div key={pi} className="flex gap-1 flex-wrap">
                              {Object.entries(p.ppe).map(([cls, conf]) => (
                                <span
                                  key={cls}
                                  className={`px-1.5 py-0.5 text-[8px] font-bold uppercase border ${cls.startsWith("no_")
                                      ? "border-red-800 text-red-400"
                                      : "border-emerald-900 text-emerald-500"
                                    }`}
                                >
                                  {cls.replace("_", " ")} {((conf as number) * 100).toFixed(0)}%
                                </span>
                              ))}
                            </div>
                          ) : null
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
