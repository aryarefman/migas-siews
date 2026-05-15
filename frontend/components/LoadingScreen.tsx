"use client";

import { useState, useEffect } from "react";
import Image from "next/image";

export default function LoadingScreen({ message = "Loading...", onRetry }: { message?: string; onRetry?: () => void }) {
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setTimedOut(true), 30000);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-6" style={{ background: "var(--bg-base)" }}>
      <div className="relative">
        <div className="absolute inset-[-12px] rounded-full border animate-ping opacity-20" style={{ borderColor: "var(--accent)" }} />
        <Image src="/logo-siews.png" alt="SIEWS+" width={52} height={52} priority />
      </div>
      {timedOut ? (
        <div className="text-center">
          <p className="text-sm font-medium mb-3" style={{ color: "var(--text-muted)" }}>Loading is taking too long</p>
          {onRetry ? (
            <button onClick={onRetry} className="btn-primary text-xs px-6 py-2">Retry</button>
          ) : (
            <p className="text-xs" style={{ color: "var(--text-faint)" }}>Please refresh the page</p>
          )}
        </div>
      ) : (
        <>
          <div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: "var(--border)", borderTopColor: "var(--accent)" }} />
          <p className="text-xs font-medium" style={{ color: "var(--text-faint)" }}>{message}</p>
        </>
      )}
    </div>
  );
}
