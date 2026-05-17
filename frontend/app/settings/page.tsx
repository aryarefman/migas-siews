"use client";

import { useEffect, useState, useCallback } from "react";
import LoadingScreen from "@/components/LoadingScreen";
import ImageTester from "@/components/ImageTester";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface Recipient { phone: string; name: string; }
interface VideoJob { id: number; filename: string; status: string; progress: number; created_at: string; annotated_video_path?: string; }

const TABS = [
  { id: "camera", label: "Camera & Detection", icon: "M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" },
  { id: "notifications", label: "Notifications", icon: "M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" },
  { id: "model-test", label: "Model Testing", icon: "M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" },
  { id: "video", label: "Video Processing", icon: "M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z" },
];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState("camera");
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: string } | null>(null);
  const [showToken, setShowToken] = useState(false);
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [newPhone, setNewPhone] = useState("");
  const [newName, setNewName] = useState("");
  // Video processing
  const [videoJobs, setVideoJobs] = useState<VideoJob[]>([]);
  const [uploading, setUploading] = useState(false);
  const [videoProgress, setVideoProgress] = useState<Record<number, number>>({});

  const fetchSettings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/settings`);
      if (res.ok) {
        const data = await res.json();
        setSettings(data);
        if (data.recipients) {
          const phones = data.recipients.split(",").filter((p: string) => p.trim());
          setRecipients(phones.map((p: string) => {
            const parts = p.trim().split("|");
            return { phone: parts[0], name: parts[1] || "" };
          }));
        }
      }
    } catch { /* offline */ }
    finally { setLoading(false); }
  }, []);

  const fetchVideoJobs = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/video/jobs`);
      if (res.ok) setVideoJobs(await res.json());
    } catch {}
  }, []);

  useEffect(() => { fetchSettings(); fetchVideoJobs(); }, [fetchSettings, fetchVideoJobs]);

  // Poll video job progress
  useEffect(() => {
    const processing = videoJobs.filter(j => j.status === "processing" || j.status === "pending");
    if (processing.length === 0) return;
    const interval = setInterval(async () => {
      for (const job of processing) {
        try {
          const res = await fetch(`${API_URL}/video/jobs/${job.id}`);
          if (res.ok) {
            const data = await res.json();
            setVideoProgress(prev => ({ ...prev, [job.id]: data.progress }));
            if (data.status === "done" || data.status === "failed") fetchVideoJobs();
          }
        } catch {}
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [videoJobs, fetchVideoJobs]);

  const showToastMsg = (msg: string, type: string = "success") => {
    setToast({ msg, type }); setTimeout(() => setToast(null), 4000);
  };

  const saveSetting = async (key: string, value: string) => {
    try {
      await fetch(`${API_URL}/settings`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key, value }) });
    } catch {}
  };

  const handleSaveAll = async () => {
    setSaving(true);
    try {
      const toSave: Record<string, string> = {
        camera_source: settings.camera_source || "0",
        facility_name: settings.facility_name || "Offshore Platform A",
        confidence_threshold: settings.confidence_threshold || "0.5",
        detection_interval: settings.detection_interval || "3",
        notify_cooldown: settings.notify_cooldown || "300",
        fonnte_token: settings.fonnte_token || "",
      };
      for (const [key, value] of Object.entries(toSave)) await saveSetting(key, value);
      await saveSetting("recipients", recipients.map(r => r.name ? `${r.phone}|${r.name}` : r.phone).join(","));
      showToastMsg("Settings saved");
    } catch { showToastMsg("Failed to save", "error"); }
    finally { setSaving(false); }
  };

  const handleTestNotify = async () => {
    setTesting(true);
    try {
      const res = await fetch(`${API_URL}/settings/notify-test`, { method: "POST" });
      if (res.ok) showToastMsg("Test sent! Check WhatsApp.");
      else showToastMsg("Send failed", "error");
    } catch { showToastMsg("Failed", "error"); }
    finally { setTesting(false); }
  };

  const handleVideoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`${API_URL}/video/upload`, { method: "POST", body: formData });
      if (res.ok) {
        const data = await res.json();
        showToastMsg(`Video "${file.name}" uploaded. Processing started.`);
        fetchVideoJobs();
      } else {
        const err = await res.json();
        showToastMsg(err.detail || "Upload failed", "error");
      }
    } catch { showToastMsg("Upload failed", "error"); }
    finally { setUploading(false); e.target.value = ""; }
  };

  const addRecipient = () => {
    if (!newPhone.trim()) return;
    let phone = newPhone.trim();
    if (phone.startsWith("08")) phone = "62" + phone.slice(1);
    if (phone.startsWith("+62")) phone = phone.slice(1);
    if (recipients.some(r => r.phone === phone)) { showToastMsg("Already added", "error"); return; }
    setRecipients(prev => [...prev, { phone, name: newName.trim() }]);
    setNewPhone(""); setNewName("");
  };

  const updateSetting = (key: string, value: string) => setSettings(prev => ({ ...prev, [key]: value }));

  if (loading) return <LoadingScreen message="Loading settings..." />;

  return (
    <div className="min-h-screen p-5 max-w-5xl mx-auto animate-fade-in">
      {toast && (
        <div className={`fixed top-20 right-4 z-50 px-4 py-3 rounded-xl shadow-2xl text-sm font-medium ${
          toast.type === "error" ? "bg-red-500/15 border border-red-500/25 text-red-400" : "bg-emerald-500/15 border border-emerald-500/25 text-emerald-400"
        }`}>{toast.msg}</div>
      )}

      <div className="flex gap-6">
        {/* Sidebar Tabs */}
        <nav className="w-56 flex-shrink-0">
          <h2 className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--text-faint)] mb-4 px-3">Settings</h2>
          <div className="space-y-1">
            {TABS.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium transition-all flex items-center gap-3 ${
                  activeTab === tab.id
                    ? "bg-[var(--accent)]/10 text-[var(--accent-light)] border border-[var(--accent)]/20"
                    : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-input)]"
                }`}
              >
                <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={tab.icon} />
                </svg>
                {tab.label}
              </button>
            ))}
          </div>
        </nav>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Camera & Detection */}
          {activeTab === "camera" && (
            <div className="space-y-5">
              <div className="surface-card p-6">
                <h2 className="text-sm font-semibold text-[var(--text-main)] mb-5">Camera Source</h2>
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">Source</label>
                    <input type="text" value={settings.camera_source || ""} onChange={e => updateSetting("camera_source", e.target.value)} placeholder='0 or rtsp://...' className="input-field font-mono text-sm" />
                    <p className="text-[10px] text-[var(--text-faint)] mt-1">0 = webcam, or RTSP URL for IP camera</p>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">Facility Name</label>
                    <input type="text" value={settings.facility_name || ""} onChange={e => updateSetting("facility_name", e.target.value)} className="input-field text-sm" />
                  </div>
                </div>
              </div>

              <div className="surface-card p-6">
                <h2 className="text-sm font-semibold text-[var(--text-main)] mb-5">Detection Engine</h2>
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-[var(--text-muted)] mb-2">
                      Confidence: <span className="text-[var(--accent-light)]">{parseFloat(settings.confidence_threshold || "0.5").toFixed(2)}</span>
                    </label>
                    <input type="range" min="0.3" max="0.9" step="0.05" value={settings.confidence_threshold || "0.5"} onChange={e => updateSetting("confidence_threshold", e.target.value)} className="w-full" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">Detection Interval (frames)</label>
                    <input type="number" min="1" max="10" value={settings.detection_interval || "3"} onChange={e => updateSetting("detection_interval", e.target.value)} className="input-field font-mono !w-24 text-sm" />
                  </div>
                </div>
              </div>

              <button onClick={handleSaveAll} disabled={saving} className="btn-primary w-full py-3 text-sm font-semibold">
                {saving ? "Saving..." : "Save Settings"}
              </button>
            </div>
          )}

          {/* Notifications */}
          {activeTab === "notifications" && (
            <div className="space-y-5">
              <div className="surface-card p-6">
                <h2 className="text-sm font-semibold text-[var(--text-main)] mb-5">WhatsApp (Fonnte)</h2>
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">Cooldown (seconds)</label>
                    <input type="number" min="30" max="3600" value={settings.notify_cooldown || "300"} onChange={e => updateSetting("notify_cooldown", e.target.value)} className="input-field font-mono !w-32 text-sm" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">API Token</label>
                    <div className="relative">
                      <input type={showToken ? "text" : "password"} value={settings.fonnte_token || ""} onChange={e => updateSetting("fonnte_token", e.target.value)} placeholder="Token from fonnte.com" className="input-field font-mono text-sm pr-16" />
                      <button onClick={() => setShowToken(!showToken)} className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-[var(--text-faint)]">{showToken ? "Hide" : "Show"}</button>
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-[var(--text-muted)] mb-2">Recipients</label>
                    {recipients.map(r => (
                      <div key={r.phone} className="flex items-center justify-between px-3 py-2 mb-1.5 rounded-lg bg-[var(--bg-input)] border border-[var(--border)]">
                        <span className="text-xs font-mono">{r.phone} {r.name && <span className="text-[var(--text-faint)]">[{r.name}]</span>}</span>
                        <button onClick={() => setRecipients(prev => prev.filter(x => x.phone !== r.phone))} className="text-red-400 text-xs">×</button>
                      </div>
                    ))}
                    <div className="flex gap-2 mt-2">
                      <input type="text" value={newPhone} onChange={e => setNewPhone(e.target.value)} placeholder="628..." className="input-field font-mono flex-1 text-sm" />
                      <input type="text" value={newName} onChange={e => setNewName(e.target.value)} placeholder="Name" className="input-field flex-1 text-sm" />
                      <button onClick={addRecipient} className="btn-ghost px-3 text-xs">Add</button>
                    </div>
                  </div>
                  <button onClick={handleTestNotify} disabled={testing} className="btn-ghost w-full text-xs">{testing ? "Sending..." : "Send Test Alert"}</button>
                </div>
              </div>
              <button onClick={handleSaveAll} disabled={saving} className="btn-primary w-full py-3 text-sm font-semibold">{saving ? "Saving..." : "Save Settings"}</button>
            </div>
          )}

          {/* Model Testing */}
          {activeTab === "model-test" && (
            <div className="surface-card p-6">
              <h2 className="text-sm font-semibold text-[var(--text-main)] mb-2">Model Testing</h2>
              <p className="text-xs text-[var(--text-muted)] mb-4">Upload an image to test all detection models (Person, PPE, Fire/Smoke, Vehicle, Road)</p>
              <ImageTester />
            </div>
          )}

          {/* Video Processing */}
          {activeTab === "video" && (
            <div className="space-y-5">
              <div className="surface-card p-6">
                <h2 className="text-sm font-semibold text-[var(--text-main)] mb-2">Video Analysis</h2>
                <p className="text-xs text-[var(--text-muted)] mb-5">Upload a video file — AI will process each frame and output an annotated video with all detections labeled.</p>

                <label className={`block w-full text-center py-6 rounded-lg border-2 border-dashed transition-all cursor-pointer ${uploading ? "border-[var(--accent)]/50 bg-[var(--accent)]/5" : "border-[var(--border)] hover:border-[var(--accent)]/30 hover:bg-[var(--accent)]/5"}`}>
                  <input type="file" className="hidden" accept="video/mp4,video/avi,video/mkv,video/mov,video/webm" onChange={handleVideoUpload} disabled={uploading} />
                  {uploading ? (
                    <div className="flex flex-col items-center gap-2">
                      <div className="w-5 h-5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
                      <span className="text-xs text-[var(--accent-light)]">Uploading...</span>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-2">
                      <svg className="w-8 h-8 text-[var(--text-faint)]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" /></svg>
                      <span className="text-xs font-medium text-[var(--text-muted)]">Drop video or click to upload</span>
                      <span className="text-[10px] text-[var(--text-faint)]">MP4, AVI, MKV, MOV, WebM</span>
                    </div>
                  )}
                </label>
              </div>

              {/* Job List */}
              {videoJobs.length > 0 && (
                <div className="surface-card p-6">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">Processing Jobs</h3>
                    {videoJobs.length > 0 && (
                      <button
                        onClick={async () => {
                          if (!confirm("Delete all video jobs and files?")) return;
                          for (const job of videoJobs) {
                            try { await fetch(`${API_URL}/video/jobs/${job.id}`, { method: "DELETE" }); } catch {}
                          }
                          fetchVideoJobs();
                          showToastMsg("All video jobs deleted");
                        }}
                        className="btn-danger text-[10px] py-1 px-2"
                      >
                        Delete All
                      </button>
                    )}
                  </div>
                  <div className="space-y-3">
                    {videoJobs.map(job => (
                      <div key={job.id} className="p-4 rounded-lg bg-[var(--bg-input)] border border-[var(--border)]">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-medium text-[var(--text-main)] truncate max-w-[200px]">{job.filename}</span>
                          <div className="flex items-center gap-2">
                            <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                              job.status === "done" ? "bg-emerald-500/15 text-emerald-400" :
                              job.status === "failed" ? "bg-red-500/15 text-red-400" :
                              job.status === "processing" ? "bg-amber-500/15 text-amber-400" :
                              "bg-gray-500/15 text-gray-400"
                            }`}>{job.status}</span>
                            <button
                              onClick={async () => {
                                try {
                                  await fetch(`${API_URL}/video/jobs/${job.id}`, { method: "DELETE" });
                                  fetchVideoJobs();
                                  showToastMsg("Video job deleted");
                                } catch { showToastMsg("Delete failed", "error"); }
                              }}
                              className="p-1 rounded hover:bg-red-500/10 text-[var(--text-faint)] hover:text-red-400 transition-all"
                              title="Delete job"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                            </button>
                          </div>
                        </div>
                        {(job.status === "processing" || job.status === "pending") && (
                          <div className="w-full h-1.5 bg-[var(--border)] rounded-full overflow-hidden">
                            <div className="h-full bg-[var(--accent)] rounded-full transition-all duration-500" style={{ width: `${videoProgress[job.id] || job.progress || 0}%` }} />
                          </div>
                        )}
                        {job.status === "done" && (
                          <div className="flex items-center gap-3 mt-2">
                            <a href={`${API_URL}/video/annotated/${job.id}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-xs text-[var(--accent-light)] hover:underline">
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                              Download
                            </a>
                            <button
                              onClick={async () => {
                                try {
                                  const res = await fetch(`${API_URL}/video/jobs/${job.id}/reprocess`, { method: "POST" });
                                  if (res.ok) {
                                    showToastMsg("Re-processing started with current zones");
                                    fetchVideoJobs();
                                  } else {
                                    const err = await res.json();
                                    showToastMsg(err.detail || "Re-process failed", "error");
                                  }
                                } catch { showToastMsg("Re-process failed", "error"); }
                              }}
                              className="inline-flex items-center gap-1.5 text-xs text-amber-400 hover:text-amber-300 transition-colors"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                              Re-process
                            </button>
                          </div>
                        )}
                        <p className="text-[10px] text-[var(--text-faint)] mt-1">{new Date(job.created_at).toLocaleString()}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
