"use client";

import { useEffect, useState, useCallback } from "react";
import LoadingScreen from "@/components/LoadingScreen";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface Zone {
  id: number;
  name: string;
  risk_level: string;
  color: string;
  is_active: boolean;
}

export default function ZonesPage() {
  const [zones, setZones] = useState<Zone[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchZones = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/polygons`);
      if (res.ok) setZones(await res.json());
    } catch (err) { console.error(err); }
    finally { setTimeout(() => setLoading(false), 1000); }
  }, []);

  useEffect(() => { fetchZones(); }, [fetchZones]);

  const toggleZone = async (id: number, active: boolean) => {
    try {
      await fetch(`${API_URL}/polygons/${id}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !active }),
      });
      fetchZones();
    } catch (err) { console.error(err); }
  };

  const deleteZone = async (id: number) => {
    if (!confirm("Delete this monitoring zone?")) return;
    try {
      await fetch(`${API_URL}/polygons/${id}`, { method: "DELETE" });
      fetchZones();
    } catch (err) { console.error(err); }
  };

  const triggerManualShutdown = async (zoneName: string) => {
    if (!confirm(`CAUTION: MANUALLY TRIGGER SHUTDOWN FOR AREA: ${zoneName}?`)) return;
    try {
      await fetch(`${API_URL}/shutdown/trigger`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ zone_name: zoneName, reason: "Manual Emergency Trigger" }),
      });
    } catch (err) { console.error(err); }
  };

  if (loading) return <LoadingScreen message="SCAN: MAPPING GEOSPATIAL ZONES" />;

  return (
    <div className="min-h-screen p-5 max-w-6xl mx-auto animate-fade-in">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <svg className="w-4 h-4 text-amber-400" fill="currentColor" viewBox="0 0 24 24">
              <path d="M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z"/>
            </svg>
          </div>
          <h1 className="text-xl font-extrabold text-white tracking-tight">Restricted Zones</h1>
        </div>
        <p className="text-[10px] text-industrial-500 font-semibold uppercase tracking-wider ml-11">Authorized monitoring areas and risk definitions</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {(zones?.length || 0) === 0 ? (
          <div className="col-span-full py-24 rounded-xl border-2 border-dashed border-[#162033] flex flex-col items-center">
            <svg className="w-12 h-12 text-industrial-600 mb-4 opacity-30" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-5-9h10v2H7z"/>
            </svg>
            <p className="text-xs font-bold text-industrial-600 uppercase tracking-wider">No Monitoring Zones Active</p>
          </div>
        ) : (
          zones?.map((zone) => (
            <div key={zone.id} className="rounded-xl bg-[#0c1220]/80 border border-[#162033] overflow-hidden hover:border-[#1c3055] transition-all duration-300">
              <div className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-3 h-3 rounded-full flex-shrink-0 ring-2 ring-offset-2 ring-offset-[#0c1220]" style={{ backgroundColor: zone.color, ringColor: zone.color + '40' }} />
                    <h3 className="text-sm font-bold text-white truncate">{zone.name}</h3>
                  </div>
                  <span className={zone.risk_level === "high" ? "badge-high" : "badge-low"}>{zone.risk_level}</span>
                </div>

                <div className="space-y-4">
                  <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider">
                    <span className="text-industrial-500">System State</span>
                    <span className={zone.is_active ? "text-emerald-400" : "text-red-400"}>
                      {zone.is_active ? "Operational" : "Deactivated"}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 pt-1">
                    <button
                      onClick={() => toggleZone(zone.id, zone.is_active)}
                      className={`py-2.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all border ${
                        zone.is_active
                          ? "bg-[#0f1729] border-[#1c2a42] text-industrial-400 hover:text-white"
                          : "bg-emerald-500/15 border-emerald-500/30 text-emerald-400"
                      }`}
                    >{zone.is_active ? "Disable" : "Enable"}</button>
                    <button
                      onClick={() => deleteZone(zone.id)}
                      className="py-2.5 rounded-lg bg-[#070d18] border border-[#1c2a42] text-industrial-500 hover:text-red-400 hover:border-red-500/30 text-[10px] font-bold uppercase tracking-wider transition-all"
                    >Delete</button>
                  </div>

                  {zone.risk_level === "high" && (
                    <button
                      onClick={() => triggerManualShutdown(zone.name)}
                      className="w-full py-2.5 rounded-lg bg-red-500/8 border border-red-500/20 text-red-400 hover:bg-red-500/20 text-[10px] font-bold uppercase tracking-wider transition-all"
                    >Manual Shutdown</button>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
