"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface Stats {
  active_zones: number;
  today_alerts: number;
  unresolved_alerts: number;
  camera_status: string;
}

export default function Navbar() {
  const pathname = usePathname();
  const [stats, setStats] = useState<Stats>({
    active_zones: 0,
    today_alerts: 0,
    unresolved_alerts: 0,
    camera_status: "offline",
  });

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch(`${API_URL}/stats`);
        if (res.ok) setStats(await res.json());
      } catch { /* backend offline */ }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, []);

  const navLinks = [
    { href: "/dashboard", label: "Dashboard", iconPath: "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z" },
    { href: "/faces", label: "Personnel", iconPath: "M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" },
    { href: "/incidents", label: "Incidents", iconPath: "M19 3h-4.18C14.4 1.84 13.3 1 12 1s-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z" },
    { href: "/zones", label: "Zones", iconPath: "M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z" },
    { href: "/settings", label: "Settings", iconPath: "M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z" },
  ];

  return (
    <nav className="fixed top-3 left-4 right-4 z-50 bg-[#0c1220]/85 backdrop-blur-xl border border-[#1c2a42]/60 rounded-2xl shadow-xl shadow-black/30">
      <div className="max-w-[1920px] mx-auto px-5">
        <div className="flex items-center justify-between h-12">
          {/* Logo */}
          <Link href="/dashboard" className="flex items-center gap-3 group">
            <div className="relative">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-400 to-amber-600 flex items-center justify-center shadow-lg shadow-amber-500/20 group-hover:shadow-amber-500/40 transition-shadow">
                <span className="text-white font-black text-sm tracking-tight">S+</span>
              </div>
            </div>
            <div className="hidden sm:block">
              <h1 className="text-[13px] font-extrabold text-white tracking-[0.15em] leading-none">
                SIEWS<span className="text-amber-400">+</span>
              </h1>
              <p className="text-[8px] text-industrial-500 font-semibold uppercase tracking-[0.2em] mt-0.5">
                industrial safety
              </p>
            </div>
          </Link>

          {/* Navigation */}
          <div className="flex items-center gap-1">
            {navLinks.map((link) => {
              const isActive = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`
                    relative px-3.5 py-2 rounded-lg flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider transition-all duration-200
                    ${isActive
                      ? "bg-amber-500/15 text-amber-400 border border-amber-500/20"
                      : "text-industrial-400 hover:text-industrial-200 hover:bg-[#0f1729]"
                    }
                  `}
                >
                  <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                    <path d={link.iconPath} />
                  </svg>
                  <span className="hidden lg:inline">{link.label}</span>
                  {link.label === "Incidents" && stats.unresolved_alerts > 0 && (
                    <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] rounded-full bg-red-500 text-white text-[9px] font-bold flex items-center justify-center shadow-lg shadow-red-500/30 animate-pulse">
                      {stats.unresolved_alerts > 9 ? "9+" : stats.unresolved_alerts}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>

          {/* Status Chips */}
          <div className="hidden md:flex items-center gap-2">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#0c1220]/60 border border-[#162033]/60">
              <span className={`status-dot ${stats.camera_status === "online" ? "online" : "offline"}`} />
              <span className="text-[10px] font-semibold text-industrial-400 tracking-wide">
                Camera: <span className={stats.camera_status === "online" ? "text-emerald-400" : "text-red-400"}>
                  {(stats.camera_status || "offline").toUpperCase()}
                </span>
              </span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#0c1220]/60 border border-[#162033]/60">
              <span className="text-[10px] font-semibold text-industrial-400 tracking-wide">Zones:</span>
              <span className="text-[10px] font-bold text-amber-400 font-mono">{stats.active_zones}</span>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#0c1220]/60 border border-[#162033]/60">
              <span className="text-[10px] font-semibold text-industrial-400 tracking-wide">Today:</span>
              <span className="text-[10px] font-bold text-red-400 font-mono">{stats.today_alerts}</span>
            </div>
          </div>
        </div>
      </div>
    </nav>
  );
}
