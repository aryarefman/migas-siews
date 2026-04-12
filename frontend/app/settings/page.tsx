"use client";

import { useEffect, useState, useCallback } from "react";
import LoadingScreen from "@/components/LoadingScreen";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Recipient {
  phone: string;
  name: string;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: string } | null>(null);
  const [showToken, setShowToken] = useState(false);

  // Recipients management
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

        // Parse recipients
        if (data.recipients) {
          const phones = data.recipients.split(",").filter((p: string) => p.trim());
          setRecipients(phones.map((p: string) => {
            const parts = p.trim().split("|");
            return { phone: parts[0], name: parts[1] || "" };
          }));
        }
      }
    } catch {
      /* offline */
    } finally {
      setTimeout(() => setLoading(false), 1000);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const showToast = (msg: string, type: string = "success") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const saveSetting = async (key: string, value: string) => {
    try {
      await fetch(`${API_URL}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, value }),
      });
    } catch (err) {
      console.error(err);
    }
  };

  const handleSaveAll = async () => {
    setSaving(true);
    try {
      // Save all settings
      const settingsToSave = {
        camera_source: settings.camera_source || "0",
        facility_name: settings.facility_name || "Offshore Platform A",
        confidence_threshold: settings.confidence_threshold || "0.5",
        detection_interval: settings.detection_interval || "3",
        notify_cooldown: settings.notify_cooldown || "300",
        fonnte_token: settings.fonnte_token || "",
      };

      for (const [key, value] of Object.entries(settingsToSave)) {
        await saveSetting(key, value);
      }

      // Save recipients
      const recipientStr = recipients.map((r) =>
        r.name ? `${r.phone}|${r.name}` : r.phone
      ).join(",");
      await saveSetting("recipients", recipientStr);

      showToast("✅ Pengaturan berhasil disimpan");
    } catch {
      showToast("❌ Gagal menyimpan pengaturan", "error");
    } finally {
      setSaving(false);
    }
  };

  const handleTestNotify = async () => {
    setTesting(true);
    try {
      const res = await fetch(`${API_URL}/settings/notify-test`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        showToast("✅ Pesan test terkirim! Cek WhatsApp Anda.");
      } else {
        showToast(`❌ ${JSON.stringify(data)}`, "error");
      }
    } catch {
      showToast("❌ Gagal mengirim test message", "error");
    } finally {
      setTesting(false);
    }
  };

  const addRecipient = () => {
    if (!newPhone.trim()) return;
    let phone = newPhone.trim();
    // Auto format: if starts with 08, replace with 628
    if (phone.startsWith("08")) phone = "62" + phone.slice(1);
    if (phone.startsWith("+62")) phone = phone.slice(1);

    if (recipients.some((r) => r.phone === phone)) {
      showToast("⚠️ Nomor sudah terdaftar", "error");
      return;
    }

    setRecipients((prev) => [...prev, { phone, name: newName.trim() }]);
    setNewPhone("");
    setNewName("");
  };

  const removeRecipient = (phone: string) => {
    setRecipients((prev) => prev.filter((r) => r.phone !== phone));
  };

  const updateSetting = (key: string, value: string) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  if (loading) return <LoadingScreen message="BOOT: CONFIGURING SYSTEM PARAMETERS" />;

  return (
    <div className="min-h-screen p-4 max-w-3xl mx-auto">
      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-20 right-4 z-50 px-4 py-3 rounded-lg shadow-2xl animate-slide-in text-sm font-medium ${
            toast.type === "error"
              ? "bg-red-500/20 border border-red-500/30 text-red-300"
              : "bg-green-500/20 border border-green-500/30 text-green-300"
          }`}
        >
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-black text-white flex items-center gap-3">
          <svg className="w-6 h-6 text-amber-500" fill="currentColor" viewBox="0 0 24 24"><path d="M19.43 12.98c.04-.32.07-.64.07-.98s-.03-.66-.07-.98l2.11-1.65c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.39-.3-.61-.22l-2.49 1c-.52-.4-1.08-.73-1.69-.98l-.38-2.65C14.46 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42l-.38 2.65c-.61.25-1.17.59-1.69.98l-2.49-1c-.23-.09-.49 0-.61.22l-2 3.46c-.13.22-.07.49.12.64l2.11 1.65c-.04.32-.07.65-.07.98s.03.66.07.98l-2.11 1.65c-.19.15-.24.42-.12.64l2 3.46c.12.22.39.3.61.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65c.61-.25 1.17-.59 1.69-.98l2.49 1c.23.09.49 0 .61-.22l2-3.46c.12-.22.07-.49-.12-.64l-2.11-1.65zM12 15.5c-1.93 0-3.5-1.57-3.5-3.5s1.57-3.5 3.5-3.5 3.5 1.57 3.5 3.5-1.57 3.5-3.5 3.5z"/></svg>
          SYSTEM SETTINGS
        </h1>
        <p className="text-[10px] text-industrial-500 font-bold uppercase tracking-widest mt-1">
          Configuration panel for camera, detection, and connectivity
        </p>
      </div>

      <div className="space-y-6">
        {/* Camera & Facility */}
        <div className="glass-card p-6">
          <h2 className="text-[10px] font-black text-white uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
            <svg className="w-3.5 h-3.5 text-amber-500" fill="currentColor" viewBox="0 0 24 24"><path d="M12 7V3H2v18h20V7H12zM6 19H4v-2h2v2zm0-4H4v-2h2v2zm0-4H4V9h2v2zm0-4H4V5h2v2zm10 12h-2v-2h2v2zm0-4h-2v-2h2v2zm0-4h-2V9h2v2zm4 8h-2v-2h2v2zm0-4h-2v-2h2v2z"/></svg>
            Camera & Site
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-industrial-400 mb-1.5">Camera Source</label>
              <input
                type="text"
                value={settings.camera_source || ""}
                onChange={(e) => updateSetting("camera_source", e.target.value)}
                placeholder="0 (webcam) atau rtsp://..."
                className="input-field font-mono"
              />
              <p className="text-[11px] text-industrial-600 mt-1">
                Gunakan &quot;0&quot; untuk webcam lokal atau URL RTSP untuk IP camera
              </p>
            </div>
            <div>
              <label className="block text-sm text-industrial-400 mb-1.5">Nama Fasilitas</label>
              <input
                type="text"
                value={settings.facility_name || ""}
                onChange={(e) => updateSetting("facility_name", e.target.value)}
                placeholder="e.g., Offshore Platform A"
                className="input-field"
              />
            </div>
          </div>
        </div>

        {/* Detection Settings */}
        <div className="glass-card p-6">
          <h2 className="text-[10px] font-black text-white uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
            <svg className="w-3.5 h-3.5 text-amber-500" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/></svg>
            Inference Engine
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-[10px] font-bold text-industrial-500 uppercase tracking-widest mb-2">
                Confidence Threshold:{" "}
                <span className="text-amber-400 font-black">
                  {parseFloat(settings.confidence_threshold || "0.5").toFixed(2)}
                </span>
              </label>
              <input
                type="range"
                min="0.3"
                max="0.9"
                step="0.05"
                value={settings.confidence_threshold || "0.5"}
                onChange={(e) => updateSetting("confidence_threshold", e.target.value)}
                className="w-full h-1 bg-industrial-950 appearance-none cursor-pointer accent-amber-500"
              />
            </div>
            <div>
              <label className="block text-[10px] font-bold text-industrial-500 uppercase tracking-widest mb-2">
                Detection Interval (frames)
              </label>
              <input
                type="number"
                min="1"
                max="10"
                value={settings.detection_interval || "3"}
                onChange={(e) => updateSetting("detection_interval", e.target.value)}
                className="input-field font-mono !w-24 text-xs"
              />
            </div>
          </div>
        </div>

        {/* Notification Settings */}
        <div className="glass-card p-6">
          <h2 className="text-[10px] font-black text-white uppercase tracking-[0.2em] mb-6 flex items-center gap-2">
            <svg className="w-3.5 h-3.5 text-amber-500" fill="currentColor" viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/></svg>
            WhatsApp Alert Gateway
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-industrial-400 mb-1.5">
                Notify Cooldown (detik)
              </label>
              <input
                type="number"
                min="30"
                max="3600"
                value={settings.notify_cooldown || "300"}
                onChange={(e) => updateSetting("notify_cooldown", e.target.value)}
                className="input-field font-mono !w-32"
              />
              <p className="text-[11px] text-industrial-600 mt-1">
                Jeda minimum antar notifikasi per zona ({Math.floor(parseInt(settings.notify_cooldown || "300") / 60)} menit)
              </p>
            </div>
            <div>
              <label className="block text-sm text-industrial-400 mb-1.5">Fonnte API Token</label>
              <div className="relative">
                <input
                  type={showToken ? "text" : "password"}
                  value={settings.fonnte_token || ""}
                  onChange={(e) => updateSetting("fonnte_token", e.target.value)}
                  placeholder="Token dari fonnte.com"
                  className="input-field font-mono pr-16"
                />
                <button
                  onClick={() => setShowToken(!showToken)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-industrial-400 hover:text-white transition-colors px-2 py-1 rounded"
                >
                  {showToken ? "Hide" : "Show"}
                </button>
              </div>
            </div>

            {/* Recipients */}
            <div>
              <label className="block text-sm text-industrial-400 mb-2">Daftar Penerima</label>
              <div className="space-y-2 mb-3">
                {recipients.length === 0 ? (
                  <p className="text-xs text-industrial-600 italic">Belum ada penerima</p>
                ) : (
                  recipients.map((r) => (
                    <div
                      key={r.phone}
                      className="flex items-center justify-between px-3 py-2 bg-industrial-950 border border-industrial-800"
                    >
                      <div className="flex items-center gap-3">
                        <svg className="w-3 h-3 text-emerald-500" fill="currentColor" viewBox="0 0 24 24"><path d="M17 1.01L7 1c-1.1 0-2 .9-2 2v18c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V3c0-1.1-.9-1.99-2-1.99zM17 19H7V5h10v14z"/></svg>
                        <div>
                          <span className="text-[11px] font-mono text-white">{r.phone}</span>
                          {r.name && (
                            <span className="text-[10px] text-industrial-500 font-bold ml-2 uppercase">[{r.name}]</span>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={() => removeRecipient(r.phone)}
                        className="text-industrial-600 hover:text-red-500 transition-colors"
                      >
                        ✕
                      </button>
                    </div>
                  ))
                )}
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newPhone}
                  onChange={(e) => setNewPhone(e.target.value)}
                  placeholder="ID: 628..."
                  className="input-field font-mono flex-1 text-xs"
                />
                <input
                  type="text"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder="NAME"
                  className="input-field flex-1 text-xs"
                />
                <button onClick={addRecipient} className="btn-ghost !px-4 text-[10px] font-black uppercase">
                  ADD
                </button>
              </div>
            </div>

            {/* Test Button */}
            <button
              onClick={handleTestNotify}
              disabled={testing || recipients.length === 0}
              className="btn-ghost w-full flex items-center justify-center gap-2 disabled:opacity-40 text-[10px] font-black uppercase tracking-widest"
            >
              {testing ? "SENDING..." : "SEND TEST ALERT"}
            </button>
          </div>
        </div>

        {/* Save Button */}
        <button
          onClick={handleSaveAll}
          disabled={saving}
          className="btn-primary w-full py-4 text-[11px] font-black uppercase tracking-[0.3em] flex items-center justify-center gap-3"
        >
          {saving ? "SAVING..." : (
            <>
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M17 3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V7l-4-4zm-5 16c-1.66 0-3-1.34-3-3s1.34-3 3-3 3 1.34 3 3-1.34 3-3 3zm3-10H5V5h10v4z"/></svg>
              Commit Settings
            </>
          )}
        </button>
      </div>
    </div>
  );
}
