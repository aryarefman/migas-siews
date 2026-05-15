"use client";

import { useEffect, useState, useCallback } from "react";
import LoadingScreen from "@/components/LoadingScreen";
import Modal from "@/components/Modal";
import DetailPanel from "@/components/DetailPanel";
import { showToast } from "@/components/Toast";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface Zone {
  id: number;
  name: string;
  risk_level: string;
  color: string;
  active: boolean;
  vertices?: number[][];
  created_at?: string;
  zone_type?: string;
  dwell_threshold_sec?: number;
}

export default function ZonesPage() {
  const [zones, setZones] = useState<Zone[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedZone, setSelectedZone] = useState<Zone | null>(null);
  const [modal, setModal] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
    type: "danger" | "warning" | "info";
    confirmText: string;
  }>({
    isOpen: false,
    title: "",
    message: "",
    onConfirm: () => {},
    type: "info",
    confirmText: "Confirm",
  });

  // Inline edit state
  const [editName, setEditName] = useState("");
  const [editRisk, setEditRisk] = useState("");
  const [editColor, setEditColor] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [saving, setSaving] = useState(false);

  const fetchZones = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/polygons`);
      if (res.ok) setZones(await res.json());
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchZones(); }, [fetchZones]);

  const openDetail = (zone: Zone) => {
    setSelectedZone(zone);
    setEditName(zone.name);
    setEditRisk(zone.risk_level);
    setEditColor(zone.color);
    setEditActive(zone.active);
  };

  const saveEdit = async () => {
    if (!selectedZone) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/polygons/${selectedZone.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: editName,
          risk_level: editRisk,
          color: editColor,
          active: editActive,
        }),
      });
      if (res.ok) {
        showToast(`Zone "${editName}" updated`, "success");
        fetchZones();
        setSelectedZone(null);
      } else {
        showToast("Failed to update zone", "error");
      }
    } catch {
      showToast("Failed to update zone", "error");
    } finally {
      setSaving(false);
    }
  };

  const toggleZone = async (id: number, active: boolean) => {
    try {
      await fetch(`${API_URL}/polygons/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: !active }),
      });
      showToast(active ? "Zone deactivated" : "Zone activated", "success");
      fetchZones();
    } catch (err) { console.error(err); }
  };

  const deleteZone = (id: number, name: string) => {
    setModal({
      isOpen: true,
      title: "Delete Zone",
      message: `Are you sure you want to delete "${name}"? Monitoring will stop immediately.`,
      onConfirm: async () => {
        try {
          await fetch(`${API_URL}/polygons/${id}`, { method: "DELETE" });
          showToast("Zone deleted", "success");
          fetchZones();
          if (selectedZone && selectedZone.id === id) setSelectedZone(null);
        } catch (err) { console.error(err); }
      },
      type: "danger",
      confirmText: "Delete",
    });
  };

  const deleteFromDetail = () => {
    if (!selectedZone) return;
    const zone = selectedZone;
    setSelectedZone(null);
    deleteZone(zone.id, zone.name);
  };

  if (loading) return <LoadingScreen message="Loading zones..." />;

  return (
    <div className="min-h-screen p-5 max-w-5xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-xl font-bold text-[var(--text-main)] tracking-tight">Monitoring Zones</h1>
        <p className="text-sm text-[var(--text-muted)] mt-1">Manage restricted areas and risk definitions</p>
      </div>

      {/* Zone List */}
      {(zones?.length || 0) === 0 ? (
        <div className="py-24 rounded-xl border-2 border-dashed border-[var(--border)] flex flex-col items-center">
          <svg className="w-12 h-12 text-[var(--text-faint)] mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l5.447 2.724A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
          </svg>
          <p className="text-sm text-[var(--text-faint)]">No monitoring zones configured</p>
          <p className="text-xs text-[var(--text-faint)] mt-1">Draw zones on the dashboard camera view</p>
        </div>
      ) : (
        <div className="space-y-3">
          {zones.map((zone) => (
            <div
              key={zone.id}
              className="surface-card p-5 flex items-center justify-between gap-4 hover:border-[var(--border-bright)] transition-all cursor-pointer"
              onClick={() => openDetail(zone)}
            >
              <div className="flex items-center gap-4 min-w-0">
                <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: zone.color }} />
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-[var(--text-main)] truncate">{zone.name}</h3>
                  <div className="flex items-center gap-3 mt-1">
                    <span className={zone.risk_level === "high" ? "badge-high" : "badge-low"}>{zone.risk_level}</span>
                    <span className={`text-[11px] font-medium ${zone.active ? "text-emerald-500" : "text-[var(--text-faint)]"}`}>
                      {zone.active ? "Active" : "Inactive"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={(e) => { e.stopPropagation(); toggleZone(zone.id, zone.active); }}
                  className={`btn-ghost text-xs py-1.5 px-3 ${
                    zone.active ? "" : "text-emerald-500 border-emerald-500/20"
                  }`}
                >
                  {zone.active ? "Disable" : "Enable"}
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); deleteZone(zone.id, zone.name); }}
                  className="btn-ghost text-xs py-1.5 px-3 hover:text-red-400 hover:border-red-500/20"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Zone Detail + Edit Overlay */}
      <DetailPanel
        isOpen={!!selectedZone}
        onClose={() => setSelectedZone(null)}
        title="Zone Detail"
        width="440px"
      >
        {selectedZone && (
          <div>
            {/* Zone info summary */}
            <div className="flex items-center gap-3 mb-5 p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
              <div className="w-5 h-5 rounded-full flex-shrink-0" style={{ backgroundColor: editColor }} />
              <div>
                <p className="text-sm font-semibold" style={{ color: "var(--text-main)" }}>{selectedZone.name}</p>
                <p className="text-[10px]" style={{ color: "var(--text-faint)" }}>
                  {selectedZone.vertices?.length || 0} vertices • Created {selectedZone.created_at ? new Date(selectedZone.created_at).toLocaleDateString() : "N/A"}
                </p>
              </div>
            </div>

            {/* Editable fields */}
            <div className="space-y-4">
              {/* Name */}
              <div>
                <label className="text-[11px] font-medium mb-1.5 block" style={{ color: "var(--text-muted)" }}>Zone Name</label>
                <input
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="input-field text-sm"
                  placeholder="Zone name"
                />
              </div>

              {/* Risk Level */}
              <div>
                <label className="text-[11px] font-medium mb-2 block" style={{ color: "var(--text-muted)" }}>Risk Level</label>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setEditRisk("high")}
                    className={`flex-1 py-2.5 rounded-lg text-xs font-medium border transition-all ${
                      editRisk === "high" ? "border-red-500/40 bg-red-500/10 text-red-400" : ""
                    }`}
                    style={editRisk !== "high" ? { borderColor: "var(--border)", color: "var(--text-faint)" } : undefined}
                  >
                    High Risk
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditRisk("low")}
                    className={`flex-1 py-2.5 rounded-lg text-xs font-medium border transition-all ${
                      editRisk === "low" ? "border-amber-500/40 bg-amber-500/10 text-amber-400" : ""
                    }`}
                    style={editRisk !== "low" ? { borderColor: "var(--border)", color: "var(--text-faint)" } : undefined}
                  >
                    Low Risk
                  </button>
                </div>
              </div>

              {/* Color presets */}
              <div>
                <label className="text-[11px] font-medium mb-1.5 block" style={{ color: "var(--text-muted)" }}>Color Presets</label>
                <div className="flex gap-2">
                  <button type="button" onClick={() => setEditColor("#ef4444")} className="w-7 h-7 rounded-full border-2 border-white/20" style={{ backgroundColor: "#ef4444" }} title="Red (High)" />
                  <button type="button" onClick={() => setEditColor("#f59e0b")} className="w-7 h-7 rounded-full border-2 border-white/20" style={{ backgroundColor: "#f59e0b" }} title="Amber (Low)" />
                  <button type="button" onClick={() => setEditColor("#3b82f6")} className="w-7 h-7 rounded-full border-2 border-white/20" style={{ backgroundColor: "#3b82f6" }} title="Blue (Caution)" />
                  <button type="button" onClick={() => setEditColor("#8b5cf6")} className="w-7 h-7 rounded-full border-2 border-white/20" style={{ backgroundColor: "#8b5cf6" }} title="Purple" />
                  <button type="button" onClick={() => setEditColor("#10b981")} className="w-7 h-7 rounded-full border-2 border-white/20" style={{ backgroundColor: "#10b981" }} title="Green" />
                </div>
              </div>

              {/* Color */}
              <div>
                <label className="text-[11px] font-medium mb-1.5 block" style={{ color: "var(--text-muted)" }}>Custom Color</label>
                <div className="flex items-center gap-3">
                  <input
                    type="color"
                    value={editColor}
                    onChange={(e) => setEditColor(e.target.value)}
                    className="w-10 h-10 rounded-lg cursor-pointer border-0 bg-transparent p-0"
                    style={{ appearance: "none", WebkitAppearance: "none" }}
                  />
                  <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{editColor}</span>
                </div>
              </div>

              {/* Zone Type */}
              <div>
                <label className="text-[11px] font-medium mb-1.5 block" style={{ color: "var(--text-muted)" }}>Zone Type</label>
                <div className="flex gap-2">
                  {["restricted", "monitoring", "caution"].map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => { const z = zones.find(z => z.id === selectedZone?.id); if (z) { setEditName(z.name); setEditRisk(z.risk_level); setEditColor(z.color); setEditActive(z.active); } }}
                      className={`px-3 py-2 rounded-lg text-[11px] font-medium border transition-all capitalize ${
                        (selectedZone as any)?.zone_type === type ? "border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--accent-light)]" : ""
                      }`}
                      style={{ borderColor: (selectedZone as any)?.zone_type === type ? undefined : "var(--border)", color: (selectedZone as any)?.zone_type === type ? undefined : "var(--text-faint)" }}
                    >
                      {type}
                    </button>
                  ))}
                </div>
                <p className="text-[10px] mt-1" style={{ color: "var(--text-faint)" }}>Restricted = immediate alert, Monitoring = dwell time, Caution = warning only</p>
              </div>

              {/* Dwell threshold */}
              <div>
                <label className="text-[11px] font-medium mb-1.5 block" style={{ color: "var(--text-muted)" }}>Dwell Alert (seconds)</label>
                <input
                  type="number"
                  min={0}
                  max={300}
                  value={0}
                  onChange={(e) => {}}
                  className="input-field text-sm"
                  placeholder="0 = immediate"
                />
                <p className="text-[10px] mt-1" style={{ color: "var(--text-faint)" }}>Time before person triggers dwell alert (0 = instant)</p>
              </div>

              {/* Active toggle */}
              <div className="flex items-center justify-between p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
                <span className="text-xs font-medium" style={{ color: "var(--text-main)" }}>Active Monitoring</span>
                <button
                  onClick={() => setEditActive(!editActive)}
                  className="relative w-10 h-[22px] rounded-full transition-colors duration-200"
                  style={{
                    backgroundColor: editActive ? "rgba(16, 185, 129, 0.3)" : "rgba(100, 116, 139, 0.2)",
                  }}
                  role="switch"
                  aria-checked={editActive}
                >
                  <div
                    className={`absolute top-[3px] w-[16px] h-[16px] rounded-full transition-all duration-200 ${
                      editActive ? "bg-emerald-400" : "bg-gray-500"
                    }`}
                    style={{ left: editActive ? "20px" : "3px" }}
                  />
                </button>
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex gap-3 mt-6">
              <button
                onClick={deleteFromDetail}
                className="py-2.5 px-4 rounded-lg text-sm font-medium transition-all border border-red-500/20 text-red-400 hover:bg-red-500/10"
              >
                Delete
              </button>
              <button
                onClick={saveEdit}
                disabled={saving || !editName.trim()}
                className="flex-1 py-2.5 rounded-lg text-sm font-medium text-white transition-all disabled:opacity-30"
                style={{ background: "var(--accent)" }}
              >
                {saving ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </div>
        )}
      </DetailPanel>

      <Modal
        isOpen={modal.isOpen}
        onClose={() => setModal({ ...modal, isOpen: false })}
        onConfirm={modal.onConfirm}
        title={modal.title}
        message={modal.message}
        confirmText={modal.confirmText}
        cancelText="Cancel"
        type={modal.type}
      />
    </div>
  );
}
