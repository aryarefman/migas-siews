"use client";

import { useState } from "react";
import { showToast } from "./Toast";
import Modal from "./Modal";
import DetailPanel from "./DetailPanel";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface ZoneData {
  id: number;
  name: string;
  vertices: number[][];
  color: string;
  active: boolean;
  risk_level: string;
  created_at?: string;
}

interface ZoneEditorProps {
  zones: ZoneData[];
  onRefresh: () => void;
  onStartDrawing: () => void;
  drawingMode: boolean;
}

export default function ZoneEditor({ zones, onRefresh, onStartDrawing, drawingMode }: ZoneEditorProps) {
  const [loading, setLoading] = useState<number | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [targetZone, setTargetZone] = useState<ZoneData | null>(null);
  const [selectedZone, setSelectedZone] = useState<ZoneData | null>(null);

  // Inline edit state
  const [editName, setEditName] = useState("");
  const [editRisk, setEditRisk] = useState("");
  const [editColor, setEditColor] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [saving, setSaving] = useState(false);

  const openDetail = (zone: ZoneData) => {
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
        onRefresh();
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

  const toggleZone = async (zone: ZoneData) => {
    setLoading(zone.id);
    try {
      await fetch(`${API_URL}/polygons/${zone.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: !zone.active }),
      });
      onRefresh();
      showToast(`Zone "${zone.name}" ${!zone.active ? "enabled" : "disabled"}`, "success");
    } catch {
      showToast("Failed to toggle zone", "error");
    } finally {
      setLoading(null);
    }
  };

  const deleteZone = (zone: ZoneData) => {
    setTargetZone(zone);
    setModalOpen(true);
  };

  const confirmDelete = async () => {
    if (!targetZone) return;
    setLoading(targetZone.id);
    try {
      await fetch(`${API_URL}/polygons/${targetZone.id}`, { method: "DELETE" });
      onRefresh();
      showToast(`Zone "${targetZone.name}" deleted`, "success");
      if (selectedZone && selectedZone.id === targetZone.id) {
        setSelectedZone(null);
      }
    } catch {
      showToast("Failed to delete zone", "error");
    } finally {
      setLoading(null);
      setTargetZone(null);
    }
  };

  const deleteFromDetail = () => {
    if (!selectedZone) return;
    setSelectedZone(null);
    setTargetZone(selectedZone);
    setModalOpen(true);
  };

  return (
    <div className="flex flex-col">
      {/* Add Zone Button */}
      <div className="p-3">
        <button
          onClick={onStartDrawing}
          disabled={drawingMode}
          className={`w-full py-2.5 rounded-lg text-xs font-semibold transition-all ${
            drawingMode
              ? "bg-[var(--accent)]/10 text-[var(--accent-light)] border border-[var(--accent)]/20 cursor-not-allowed"
              : "bg-[var(--accent)] text-white hover:bg-[var(--accent-light)] shadow-md shadow-[var(--accent)]/20"
          }`}
        >
          {drawingMode ? "Drawing..." : "+ Add Zone"}
        </button>
      </div>

      {/* Zone List */}
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1.5">
        {zones.length === 0 ? (
          <div className="text-center py-10">
            <p className="text-[11px] text-gray-500 font-medium">No zones defined</p>
            <p className="text-[10px] text-gray-600 mt-1">Click + Add Zone to create one</p>
          </div>
        ) : (
          zones.map((zone) => (
            <div
              key={zone.id}
              className={`p-3 rounded-xl border transition-all duration-200 cursor-pointer ${
                zone.active
                  ? "bg-white/[0.02] border-white/[0.06] hover:border-white/10"
                  : "bg-black/20 border-white/[0.03] opacity-50"
              }`}
              onClick={() => openDetail(zone)}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ backgroundColor: zone.color }}
                  />
                  <div className="min-w-0">
                    <p className="text-[12px] font-medium text-white truncate">{zone.name}</p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <span className={zone.risk_level === "high" ? "badge-high" : "badge-low"}>
                        {zone.risk_level}
                      </span>
                      <span className="text-[9px] text-gray-600 font-mono">
                        {zone.vertices?.length || 0}pts
                      </span>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 flex-shrink-0">
                  <button
                    onClick={(e) => { e.stopPropagation(); toggleZone(zone); }}
                    disabled={loading === zone.id}
                    className="relative w-8 h-[18px] rounded-full transition-colors duration-200"
                    style={{
                      backgroundColor: zone.active ? "rgba(16, 185, 129, 0.3)" : "rgba(100, 116, 139, 0.2)",
                    }}
                    role="switch"
                    aria-checked={zone.active}
                    aria-label={`${zone.active ? "Disable" : "Enable"} zone ${zone.name}`}
                  >
                    <div
                      className={`absolute top-[2px] w-[14px] h-[14px] rounded-full transition-all duration-200 ${
                        zone.active ? "bg-emerald-400" : "bg-gray-500"
                      }`}
                      style={{ left: zone.active ? "16px" : "2px" }}
                    />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteZone(zone); }}
                    disabled={loading === zone.id}
                    className="p-1 rounded-md hover:bg-red-500/10 text-gray-500 hover:text-red-400 transition-colors"
                    aria-label={`Delete zone ${zone.name}`}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Zone Detail + Edit Overlay */}
      <DetailPanel
        isOpen={!!selectedZone}
        onClose={() => setSelectedZone(null)}
        title="Zone Detail"
        width="420px"
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

              {/* Color */}
              <div>
                <label className="text-[11px] font-medium mb-1.5 block" style={{ color: "var(--text-muted)" }}>Color</label>
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
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onConfirm={confirmDelete}
        title="Delete Monitoring Zone"
        message={`Are you sure you want to delete zone "${targetZone?.name}"? Monitoring for this area will stop immediately.`}
        confirmText="Delete"
        cancelText="Cancel"
        type="danger"
      />
    </div>
  );
}
