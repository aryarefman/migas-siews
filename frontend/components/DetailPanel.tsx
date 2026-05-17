"use client";

import { ReactNode } from "react";

interface DetailPanelProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  width?: string;
}

export default function DetailPanel({ isOpen, onClose, title, children, width }: DetailPanelProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div
        className="relative w-full max-h-[85vh] overflow-y-auto rounded-2xl border shadow-2xl animate-fade-in"
        style={{
          maxWidth: width || "480px",
          background: "var(--bg-surface)",
          borderColor: "var(--border)",
        }}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between p-4 border-b" style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}>
          <h2 className="text-sm font-bold uppercase tracking-wider" style={{ color: "var(--text-main)" }}>{title || "Detail"}</h2>
          <button onClick={onClose} className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--bg-input)] transition-all" style={{ color: "var(--text-muted)" }}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
