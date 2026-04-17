"use client";

import { useEffect, useState } from "react";
import LoadingScreen from "@/components/LoadingScreen";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface FaceEntry {
  id: string;
  name: string;
  code: string;
  image_url: string;
  registered_at: string;
}

export default function FacesPage() {
  const [loading, setLoading] = useState(true);
  const [faces, setFaces] = useState<FaceEntry[]>([]);
  const [uploading, setUploading] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [phone, setPhone] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const fetchFaces = async () => {
    try {
      const res = await fetch(`${API_URL}/faces`);
      if (res.ok) setFaces(await res.json());
    } catch (err) {
      console.error("Failed to fetch faces", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchFaces(); }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setPreviewUrl(URL.createObjectURL(file));
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || !name || !phone) return;
    setUploading(true);
    const formData = new FormData();
    formData.append("file", selectedFile);
    try {
      const res = await fetch(`${API_URL}/faces/register?name=${encodeURIComponent(name)}&code=${encodeURIComponent(code)}&phone=${encodeURIComponent(phone)}`, {
        method: "POST", body: formData,
      });
      if (res.ok) {
        setName(""); setCode(""); setPhone("");
        setSelectedFile(null); setPreviewUrl(null);
        fetchFaces();
      } else {
        const err = await res.json();
        alert(`Gagal: ${err.detail}`);
      }
    } catch (err) { console.error("Upload error", err); }
    finally { setUploading(false); }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Hapus data wajah ini?")) return;
    try {
      const res = await fetch(`${API_URL}/faces/${id}`, { method: "DELETE" });
      if (res.ok) fetchFaces();
    } catch (err) { console.error("Delete error", err); }
  };

  const handleTrain = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/faces/train`, { method: "POST" });
      if (res.ok) alert("Training data wajah berhasil disinkronkan!");
    } catch (err) { console.error("Train error", err); }
    finally { setLoading(false); }
  };

  if (loading && faces.length === 0) return <LoadingScreen message="SYST_SYNC: FETCHING BIOMETRIC DATABASE" />;

  return (
    <div className="min-h-screen p-5 max-w-[1400px] mx-auto animate-fade-in">
      {/* Header */}
      <header className="mb-10 flex flex-col sm:flex-row justify-between items-start sm:items-end gap-4 border-b border-[#162033] pb-8">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="w-1.5 h-7 rounded-full bg-gradient-to-b from-amber-400 to-amber-600" />
            <h1 className="text-2xl font-extrabold tracking-tight text-white">Biometric Registry</h1>
          </div>
          <p className="text-industrial-500 text-xs font-semibold tracking-[0.15em] uppercase">Personnel Digital Identity Management</p>
        </div>
        <button
          onClick={handleTrain}
          className="px-5 py-2.5 rounded-lg bg-[#0c1220] border border-amber-500/20 text-amber-400 text-[11px] font-bold uppercase tracking-wider hover:bg-amber-500/10 transition-all flex items-center gap-2 group"
        >
          <svg className="w-4 h-4 group-hover:rotate-180 transition-transform duration-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Sync & Train
        </button>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
        {/* Registration Form */}
        <section className="lg:col-span-4 rounded-xl bg-[#0c1220]/80 border border-[#162033] p-6 h-fit sticky top-24">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.2em] mb-6 text-industrial-400 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
            New Registration
          </h2>

          <form onSubmit={handleRegister} className="space-y-5">
            <div className="group">
              <label className="block text-[10px] font-semibold text-industrial-500 uppercase tracking-widest mb-2 group-focus-within:text-amber-400 transition-colors">Personnel Name</label>
              <input
                type="text" value={name} onChange={e => setName(e.target.value)}
                placeholder="e.g. ARYA REFMAN"
                className="input-field font-mono text-xs" required
              />
            </div>
            <div className="group">
              <label className="block text-[10px] font-semibold text-industrial-500 uppercase tracking-widest mb-2 group-focus-within:text-amber-400 transition-colors">Uniform / Employee ID</label>
              <input type="text" value={code} onChange={e => setCode(e.target.value)} placeholder="e.g. P80" className="input-field font-mono text-xs" />
            </div>
            <div className="group">
              <label className="block text-[10px] font-semibold text-industrial-500 uppercase tracking-widest mb-2 group-focus-within:text-amber-400 transition-colors">WhatsApp Number</label>
              <input type="text" value={phone} onChange={e => setPhone(e.target.value)} placeholder="e.g. 62812345678" className="input-field font-mono text-xs" required />
            </div>
            <div>
              <label className="block text-[10px] font-semibold text-industrial-500 uppercase tracking-widest mb-3">Facial Capture</label>
              <div className="relative group cursor-pointer">
                <input type="file" onChange={handleFileChange} accept="image/*" className="absolute inset-0 opacity-0 cursor-pointer z-10" required />
                {previewUrl ? (
                  <div className="aspect-square rounded-xl border-2 border-dashed border-amber-500/40 overflow-hidden bg-black">
                    <img src={previewUrl} alt="Preview" className="w-full h-full object-cover opacity-80" />
                  </div>
                ) : (
                  <div className="aspect-square rounded-xl border-2 border-dashed border-[#1c2a42] flex flex-col items-center justify-center gap-3 group-hover:border-amber-500/40 bg-[#070d18] transition-all">
                    <svg className="w-8 h-8 text-industrial-600 group-hover:text-amber-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    <span className="text-[9px] font-bold uppercase tracking-widest text-industrial-600 group-hover:text-amber-400 transition-colors">Select Biometric Image</span>
                  </div>
                )}
              </div>
            </div>
            <button
              type="submit" disabled={uploading || !selectedFile || !name || !phone}
              className="btn-primary w-full py-3 text-[11px] uppercase tracking-[0.2em] disabled:opacity-20"
            >
              {uploading ? "Synchronizing..." : "Register Personnel"}
            </button>
          </form>
        </section>

        {/* Face Directory */}
        <section className="lg:col-span-8">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.2em] mb-6 text-industrial-400 flex items-center gap-2">
            <div className="w-1 h-4 rounded-full bg-amber-400" />
            Registered Database ({(faces?.length || 0)} Personnel)
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {faces?.map(face => (
              <div key={face.id} className="rounded-xl bg-[#0c1220]/80 border border-[#162033] overflow-hidden group hover:border-amber-500/30 transition-all duration-300">
                <div className="aspect-[4/3] bg-black relative overflow-hidden">
                  <img
                    src={`${API_URL}${face.image_url}`} alt={face.name}
                    className="w-full h-full object-cover grayscale group-hover:grayscale-0 transition-all duration-500"
                  />
                  <button
                    onClick={() => handleDelete(face.id)}
                    className="absolute top-2 right-2 w-7 h-7 rounded-lg flex items-center justify-center bg-black/60 text-industrial-400 hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
                  >
                    <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12 19 6.41z"/></svg>
                  </button>
                  <div className="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-black/80 to-transparent">
                    <span className="bg-amber-500/90 text-white text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-wider">{face.code || "NO_ID"}</span>
                  </div>
                </div>
                <div className="p-3 space-y-1">
                  <h3 className="text-sm font-bold text-white truncate">{face.name}</h3>
                  <div className="flex justify-between items-center text-[9px] font-semibold text-industrial-500 tracking-wider">
                    <span className="font-mono">ID: {face.id.split('_').pop()}</span>
                    <span>{new Date(face.registered_at).toLocaleDateString()}</span>
                  </div>
                </div>
              </div>
            ))}

            {(faces?.length || 0) === 0 && (
              <div className="col-span-full py-20 rounded-xl border-2 border-dashed border-[#162033] flex flex-col items-center justify-center text-industrial-600">
                <svg className="w-16 h-16 mb-4 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
                <p className="text-xs font-bold uppercase tracking-[0.15em]">No biometric data found</p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
