"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
        if (res.ok) {
          setStats(await res.json());
        }
      } catch {
        /* backend offline */
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, []);

  const navLinks = [
    { href: "/dashboard", label: "Dashboard", icon: "📡" },
    { href: "/incidents", label: "Incidents", icon: "📋" },
    { href: "/zones", label: "Zones", icon: "🗺️" },
    { href: "/settings", label: "Settings", icon: "⚙️" },
  ];

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-industrial-950/95 backdrop-blur-md border-b border-industrial-800/50">
      <div className="max-w-[1920px] mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href="/dashboard" className="flex items-center gap-3 group">
            <div className="relative">
              <div className="w-9 h-9 rounded bg-amber-500 flex items-center justify-center">
                <span className="text-industrial-950 font-black text-lg">S+</span>
              </div>
              <div className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-emerald-400 border border-industrial-950" />
            </div>
            <div className="hidden sm:block">
              <h1 className="text-sm font-black text-white tracking-widest leading-none">
                SIEWS<span className="text-amber-500">+</span>
              </h1>
              <p className="text-[9px] text-industrial-500 font-bold uppercase tracking-tighter">
                Industrial Safety
              </p>
            </div>
          </Link>

          {/* Navigation Links */}
          <div className="flex items-center gap-2">
            {navLinks.map((link) => {
              const isActive = pathname === link.href;
              
              const getIcon = (label: string) => {
                const props = { className: "w-3.5 h-3.5", fill: "currentColor" };
                if (label === "Dashboard") return (
                  <svg {...props} viewBox="0 0 24 24"><path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/></svg>
                );
                if (label === "Incidents") return (
                  <svg {...props} viewBox="0 0 24 24"><path d="M19 3h-4.18C14.4 1.84 13.3 1 12 1s-2.4.84-2.82 2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-7 0c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm2 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg>
                );
                if (label === "Zones") return (
                  <svg {...props} viewBox="0 0 24 24"><path d="M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z"/></svg>
                );
                if (label === "Settings") return (
                  <svg {...props} viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>
                );
                return null;
              };

              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`
                    relative px-3 py-1.5 rounded flex items-center gap-2 text-[10px] font-black uppercase tracking-widest transition-all
                    ${
                      isActive
                        ? "bg-amber-500 text-industrial-950"
                        : "text-industrial-400 hover:text-white"
                    }
                  `}
                >
                  {getIcon(link.label)}
                  {link.label}
                  {link.label === "Incidents" && stats.unresolved_alerts > 0 && (
                    <span className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center animate-pulse">
                      {stats.unresolved_alerts > 9 ? "9+" : stats.unresolved_alerts}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>

          {/* Status Bar */}
          <div className="hidden md:flex items-center gap-4 text-xs">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-industrial-900/50 border border-industrial-800/50">
              <span
                className={`status-dot ${
                  stats.camera_status === "online" ? "online" : "offline"
                }`}
              />
              <span className="text-industrial-400">
                Camera:{" "}
                <span
                  className={
                    stats.camera_status === "online"
                      ? "text-green-400"
                      : "text-red-400"
                  }
                >
                  {stats.camera_status.toUpperCase()}
                </span>
              </span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-industrial-900/50 border border-industrial-800/50">
              <span className="text-industrial-400">
                Zones:{" "}
                <span className="text-amber-400 font-mono">
                  {stats.active_zones}
                </span>
              </span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-industrial-900/50 border border-industrial-800/50">
              <span className="text-industrial-400">
                Today:{" "}
                <span className="text-red-400 font-mono">
                  {stats.today_alerts}
                </span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </nav>
  );
}
