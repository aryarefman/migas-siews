"use client";

import { useEffect, useState, useCallback } from "react";
import LoadingScreen from "@/components/LoadingScreen";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
      if (res.ok) {
        const data = await res.json();
        setZones(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setTimeout(() => setLoading(false), 1000);
    }
  }, []);

  useEffect(() => {
    fetchZones();
  }, [fetchZones]);

  const toggleZone = async (id: number, active: boolean) => {
    try {
      await fetch(`${API_URL}/polygons/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !active }),
      });
      fetchZones();
    } catch (err) {
      console.error(err);
    }
  };

  const deleteZone = async (id: number) => {
    if (!confirm("Are you sure you want to delete this monitoring zone?")) return;
    try {
      await fetch(`${API_URL}/polygons/${id}`, { method: "DELETE" });
      fetchZones();
    } catch (err) {
      console.error(err);
    }
  };

  const triggerManualShutdown = async (zoneName: string) => {
    if (!confirm(`CAUTION: MANUALLY TRIGGER SHUTDOWN FOR AREA: ${zoneName}?`)) return;
    try {
      await fetch(`${API_URL}/shutdown/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ zone_name: zoneName, reason: "Manual Emergency Trigger" }),
      });
    } catch (err) {
      console.error(err);
    }
  };

  if (loading) return <LoadingScreen message="SCAN: MAPPING GEOSPATIAL ZONES" />;

  return (
    <div className="min-h-screen p-4 max-w-6xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-black text-white flex items-center gap-3">
          <svg className="w-6 h-6 text-amber-500" fill="currentColor" viewBox="0 0 24 24">
            <path d="M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z"/>
          </svg>
          RESTRICTED ZONES
        </h1>
        <p className="text-[10px] text-industrial-500 font-bold uppercase tracking-widest mt-1">
          Authorized monitoring areas and risk definitions
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {zones.length === 0 ? (
          <div className="col-span-full py-24 border border-dashed border-industrial-800 flex flex-col items-center">
             <svg className="w-12 h-12 text-industrial-800 mb-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-5-9h10v2H7z"/>
             </svg>
             <p className="text-[10px] font-black text-industrial-600 uppercase tracking-widest">No Monitoring Zones Active</p>
          </div>
        ) : (
          zones.map((zone) => (
            <div key={zone.id} className="glass-card overflow-hidden">
              <div className="p-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className="w-3 h-3 flex-shrink-0"
                      style={{ backgroundColor: zone.color }}
                    />
                    <h3 className="text-sm font-black text-white truncate uppercase tracking-tight">{zone.name}</h3>
                  </div>
                  <span className={zone.risk_level === "high" ? "badge-high" : "badge-low"}>
                    {zone.risk_level}
                  </span>
                </div>

                <div className="space-y-4">
                  <div className="flex items-center justify-between text-[11px] font-black uppercase tracking-widest">
                    <span className="text-industrial-500">System State</span>
                    <span className={zone.is_active ? "text-emerald-500" : "text-red-500"}>
                      {zone.is_active ? "OPERATIONAL" : "DEACTIVATED"}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 pt-2">
                    <button
                      onClick={() => toggleZone(zone.id, zone.is_active)}
                      className={`py-2.5 text-[10px] font-black uppercase tracking-widest transition-all ${
                        zone.is_active
                          ? "bg-industrial-800 text-industrial-400 hover:text-white"
                          : "bg-emerald-600 text-white"
                      }`}
                    >
                      {zone.is_active ? "Disable" : "Enable"}
                    </button>
                    <button
                      onClick={() => deleteZone(zone.id)}
                      className="py-2.5 bg-industrial-950 border border-industrial-800 text-industrial-600 hover:text-red-500 text-[10px] font-black uppercase tracking-widest transition-all"
                    >
                      Delete
                    </button>
                  </div>

                  {zone.risk_level === "high" && (
                    <button
                      onClick={() => triggerManualShutdown(zone.name)}
                      className="w-full py-2.5 bg-red-950 border border-red-900 text-red-500 hover:bg-red-600 hover:text-white text-[10px] font-black uppercase tracking-widest transition-all"
                    >
                      Manual Shutdown Trigger
                    </button>
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
