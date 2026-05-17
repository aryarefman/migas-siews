"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import Image from "next/image";
import { useTheme } from "@/components/ThemeProvider";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export default function Navbar() {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();
  const [stats, setStats] = useState({ unresolved_alerts: 0 });

  const fetchStats = useCallback(async () => {
    try { const r = await fetch(`${API_URL}/stats`); if (r.ok) setStats(await r.json()); } catch {}
  }, []);

  useEffect(() => {
    fetchStats();
    const i = setInterval(fetchStats, 15000);
    const h = () => fetchStats();
    window.addEventListener("siews-stats-refresh", h);
    return () => { clearInterval(i); window.removeEventListener("siews-stats-refresh", h); };
  }, [fetchStats]);

  if (pathname === "/dashboard") return null;

  const navLinks = [
    { href: "/dashboard", label: "Dashboard" },
    { href: "/faces", label: "Personnel" },
    { href: "/incidents", label: "Incidents", badge: stats.unresolved_alerts },
    { href: "/zones", label: "Zones" },
    { href: "/settings", label: "Settings" },
  ];

  return (
    <div className="fixed top-4 left-4 right-4 z-50 pointer-events-none">
      <header className="pointer-events-auto flex items-center justify-between px-5 h-12 bg-[var(--bg-glass)] backdrop-blur-2xl border border-[var(--border)] rounded-full shadow-lg max-w-[1400px] mx-auto">
        <Link href="/" className="flex items-center gap-2">
          <Image src="/logo-siews.png" alt="SIEWS+" width={22} height={22} className="rounded-md" />
          <span className="text-xs font-semibold text-[var(--text-main)] hidden sm:block">SIEWS+</span>
        </Link>
        <nav className="flex items-center gap-1">
          {navLinks.map((link) => (
            <Link key={link.href} href={link.href}
              className={`px-3.5 py-1.5 rounded-lg text-[12px] font-medium transition-all ${
                pathname === link.href ? "bg-[var(--accent)]/15 text-[var(--accent-light)]" : "text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--border)]"
              }`}>
              {link.label}
              {link.badge && link.badge > 0 ? <span className="ml-1.5 inline-flex items-center justify-center min-w-[16px] h-[16px] rounded-full bg-red-500 text-white text-[9px] font-bold px-1">{link.badge > 9 ? "9+" : link.badge}</span> : null}
            </Link>
          ))}
        </nav>
        <button onClick={toggleTheme} className="p-2 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--border)] transition-all" title="Toggle theme">
          {theme === "dark" ? (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" /></svg>
          ) : (
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" /></svg>
          )}
        </button>
      </header>
    </div>
  );
}
