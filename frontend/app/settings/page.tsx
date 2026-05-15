"use client";

import { useEffect, useState, useCallback } from "react";
import LoadingScreen from "@/components/LoadingScreen";
import ImageTester from "@/components/ImageTester";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface Recipient { phone: string; name: string; }

export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: string } | null>(null);
  const [showToken, setShowToken] = useState(false);
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [newPhone, setNewPhone] = useState("");
  const [newName, setNewName] = useState("");

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

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  const showToastMsg = (msg: string, type: string = "success") => {
    setToast({ msg, type }); setTimeout(() => setToast(null), 4000);
  };

  const saveSetting = async (key: string, value: string) => {
    try {
      await fetch(`${API_URL}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, value }),
      });
    } catch (err) { console.error(err); }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    try {
      const settingsToSave = {
        camera_source: settings.camera_source || "0",
        facility_name: settings.facility_name || "Offshore Platform A",
        confidence_threshold: settings.confidence_threshold || "0.5",
        detection_interval: settings.detection_interval || "3",
        notify_cooldown: settings.notify_cooldown || "300",
        fonnte_token: settings.fonnte_token || "",
      };
      for (const [key, value] of Object.entries(settingsToSave)) await saveSetting(key, value);
      const recipientStr = recipients.map((r) => r.name ? `${r.phone}|${r.name}` : r.phone).join(",");
      await saveSetting("recipients", recipientStr);
      showToastMsg("Settings saved successfully");
    } catch { showToastMsg("Failed to save settings", "error"); }
    finally { setSaving(false); }
  };

  const handleTestNotify = async () => {
    setTesting(true);
    try {
      const res = await fetch(`${API_URL}/settings/notify-test`, { method: "POST" });
      const data = await res.json();
      if (res.ok) showToastMsg("Test message sent! Check WhatsApp.");
      else showToastMsg(`Error: ${JSON.stringify(data)}`, "error");
    } catch { showToastMsg("Failed to send test", "error"); }
    finally { setTesting(false); }
  };

  const addRecipient = () => {
    if (!newPhone.trim()) return;
    let phone = newPhone.trim();
    if (phone.startsWith("08")) phone = "62" + phone.slice(1);
    if (phone.startsWith("+62")) phone = phone.slice(1);
    if (recipients.some((r) => r.phone === phone)) { showToastMsg("Number already registered", "error"); return; }
    setRecipients((prev) => [...prev, { phone, name: newName.trim() }]);
    setNewPhone(""); setNewName("");
  };

  const removeRecipient = (phone: string) => { setRecipients((prev) => prev.filter((r) => r.phone !== phone)); };
  const updateSetting = (key: string, value: string) => { setSettings((prev) => ({ ...prev, [key]: value })); };

  if (loading) return <LoadingScreen message="Loading settings..." />;

  return (
    <div className="min-h-screen p-5 max-w-3xl mx-auto animate-fade-in">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-20 right-4 z-50 px-4 py-3 rounded-xl shadow-2xl animate-slide-in text-sm font-medium ${
          toast.type === "error" ? "bg-red-500/15 border border-red-500/25 text-red-400" : "bg-emerald-500/15 border border-emerald-500/25 text-emerald-400"
        }`}>{toast.msg}</div>
      )}

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-xl font-bold text-[var(--text-main)] tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--text-muted)] mt-1">Camera, detection, and notification configuration</p>
      </div>

      <div className="space-y-5">
        {/* Camera & Site */}
        <div className="surface-card p-6">
          <h2 className="text-sm font-semibold text-[var(--text-main)] mb-5 flex items-center gap-2">
            <svg className="w-4 h-4 text-[var(--accent-light)]" fill="currentColor" viewBox="0 0 24 24"><path d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm10 12h-2v-2h2v2zm0-4h-2v-2h2v2zm0-4h-2V9h2v2zm4 8h-2v-2h2v2zm0-4h-2v-2h2v2z"/></svg>
            Camera & Site
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">Camera Source</label>
              <input type="text" value={settings.camera_source || ""} onChange={(e) => updateSetting("camera_source", e.target.value)} placeholder='0 (webcam) or rtsp://...' className="input-field font-mono text-sm" />
              <p className="text-[11px] text-[var(--text-faint)] mt-1">Use &quot;0&quot; for local webcam or RTSP URL for IP camera</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">Facility Name</label>
              <input type="text" value={settings.facility_name || ""} onChange={(e) => updateSetting("facility_name", e.target.value)} placeholder="Offshore Platform A" className="input-field text-sm" />
            </div>
          </div>
        </div>

        {/* Detection */}
        <div className="surface-card p-6">
          <h2 className="text-sm font-semibold text-[var(--text-main)] mb-5 flex items-center gap-2">
            <svg className="w-4 h-4 text-[var(--accent-light)]" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/></svg>
            Detection Engine
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-[var(--text-muted)] mb-2">
                Confidence Threshold: <span className="text-[var(--accent-light)] font-semibold">{parseFloat(settings.confidence_threshold || "0.5").toFixed(2)}</span>
              </label>
              <input type="range" min="0.3" max="0.9" step="0.05" value={settings.confidence_threshold || "0.5"} onChange={(e) => updateSetting("confidence_threshold", e.target.value)} className="w-full h-1.5 bg-[var(--bg-input)] rounded-full appearance-none cursor-pointer accent-[var(--accent)]" />
              <p className="text-[10px] text-[var(--text-faint)] mt-1">Higher = fewer false positives but may miss detections. At 0.5, half-confidence matches trigger alerts.</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">Detection Interval (frames)</label>
              <input type="number" min="1" max="10" value={settings.detection_interval || "3"} onChange={(e) => updateSetting("detection_interval", e.target.value)} className="input-field font-mono !w-24 text-sm" />
              <p className="text-[10px] text-[var(--text-faint)] mt-1">Analyze every N frames (at 30 FPS, N=3 means ~10 analyses/sec). Higher = less GPU load but slower response.</p>
            </div>
          </div>
        </div>

        {/* Notifications */}
        <div className="surface-card p-6">
          <h2 className="text-sm font-semibold text-[var(--text-main)] mb-5 flex items-center gap-2">
            <svg className="w-4 h-4 text-emerald-400" fill="currentColor" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/></svg>
            WhatsApp Notifications
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">Cooldown (seconds)</label>
              <input type="number" min="30" max="3600" value={settings.notify_cooldown || "300"} onChange={(e) => updateSetting("notify_cooldown", e.target.value)} className="input-field font-mono !w-32 text-sm" />
              <p className="text-[11px] text-[var(--text-faint)] mt-1">Min gap between notifications ({Math.floor(parseInt(settings.notify_cooldown || "300") / 60)} min)</p>
            </div>
            <div>
              <label className="block text-xs font-medium text-[var(--text-muted)] mb-1.5">Fonnte API Token</label>
              <div className="relative">
                <input type={showToken ? "text" : "password"} value={settings.fonnte_token || ""} onChange={(e) => updateSetting("fonnte_token", e.target.value)} placeholder="Token from fonnte.com" className="input-field font-mono text-sm pr-16" />
                <button onClick={() => setShowToken(!showToken)} className="absolute right-3 top-1/2 -translate-y-1/2 text-[11px] text-[var(--text-faint)] hover:text-[var(--text-main)] transition-colors font-medium">
                  {showToken ? "Hide" : "Show"}
                </button>
              </div>
            </div>

            {/* Recipients */}
            <div>
              <label className="block text-xs font-medium text-[var(--text-muted)] mb-2">Recipients</label>
              <div className="space-y-1.5 mb-3">
                {recipients.length === 0 ? (
                  <p className="text-xs text-[var(--text-faint)] italic">No recipients added</p>
                ) : (
                  recipients.map((r) => (
                    <div key={r.phone} className="flex items-center justify-between px-3 py-2 rounded-lg bg-[var(--bg-input)] border border-[var(--border)]">
                      <div className="flex items-center gap-3">
                        <svg className="w-3.5 h-3.5 text-emerald-400" fill="currentColor" viewBox="0 0 24 24"><path d="M17 1.01L7 1c-1.1 0-2 .9-2 2v18c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V3c0-1.1-.9-1.99-2-1.99zM17 19H7V5h10v14z"/></svg>
                        <div>
                          <span className="text-xs font-mono text-[var(--text-main)]">{r.phone}</span>
                          {r.name && <span className="text-[11px] text-[var(--text-faint)] ml-2">[{r.name}]</span>}
                        </div>
                      </div>
                      <button onClick={() => removeRecipient(r.phone)} className="text-[var(--text-faint)] hover:text-red-400 transition-colors text-sm">x</button>
                    </div>
                  ))
                )}
              </div>
              <div className="flex gap-2">
                <input type="text" value={newPhone} onChange={(e) => setNewPhone(e.target.value)} placeholder="628..." className="input-field font-mono flex-1 text-sm" />
                <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Name" className="input-field flex-1 text-sm" />
                <button onClick={addRecipient} className="btn-ghost px-4 text-xs">Add</button>
              </div>
            </div>

            <button onClick={handleTestNotify} disabled={testing || recipients.length === 0}
              className="btn-ghost w-full flex items-center justify-center gap-2 disabled:opacity-40 text-xs">
              {testing ? "Sending..." : "Send Test Alert"}
            </button>
          </div>
        </div>

        {/* Save */}
        <button onClick={handleSaveAll} disabled={saving}
          className="btn-primary w-full py-3.5 text-sm font-semibold flex items-center justify-center gap-2">
          {saving ? "Saving..." : (
            <>
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg>
              Save Settings
            </>
          )}
        </button>

        {/* Model Testing */}
        <div className="surface-card p-6">
          <h2 className="text-sm font-semibold text-[var(--text-main)] mb-2 flex items-center gap-2">
            <svg className="w-4 h-4 text-purple-400" fill="currentColor" viewBox="0 0 24 24"><path d="M5 21q-.825 0-1.413-.587T3 19V5q0-.825.587-1.413T5 3h14q.825 0 1.413.587T21 5v14q0 .825-.587 1.413T19 21H5zm0-2h14V5H5v14zm2-2h10l-3.5-4.5-2.5 3-1.5-2L7 17zm-2 2V5v14z"/></svg>
            Model Testing
          </h2>
          <p className="text-xs text-[var(--text-muted)] mb-4">Upload an image to test detection (PPE, faces, hazards)</p>
          <ImageTester />
        </div>
      </div>
    </div>
  );
}
