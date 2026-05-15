"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import LoadingScreen from "@/components/LoadingScreen";
import DetailPanel from "@/components/DetailPanel";
import { showToast } from "@/components/Toast";
import Modal from "@/components/Modal";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

interface FaceEntry { id: string; name: string; code: string; phone?: string; image_url: string; registered_at: string; }

const STEPS = [
  { id: "info", label: "Info", instruction: "Fill in personnel details" },
  { id: "front", label: "Front", instruction: "Capture face from the front" },
  { id: "right", label: "Right", instruction: "Capture face from the right side" },
  { id: "left", label: "Left", instruction: "Capture face from the left side" },
  { id: "review", label: "Review", instruction: "Review and submit" },
];

export default function FacesPage() {
  const [loading, setLoading] = useState(true);
  const [faces, setFaces] = useState<FaceEntry[]>([]);
  const [uploading, setUploading] = useState(false);
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [phone, setPhone] = useState("");
  const [photos, setPhotos] = useState<{ front: File[]; right: File[]; left: File[] }>({ front: [], right: [], left: [] });
  const [previews, setPreviews] = useState<{ front: string[]; right: string[]; left: string[] }>({ front: [], right: [], left: [] });
  const [webcamActive, setWebcamActive] = useState(false);
  const [deleteModal, setDeleteModal] = useState<{ isOpen: boolean; id: string | null }>({ isOpen: false, id: null });
  const [selectedFace, setSelectedFace] = useState<FaceEntry | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [editName, setEditName] = useState("");
  const [editCode, setEditCode] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const fetchFaces = useCallback(async () => {
    try { const r = await fetch(`${API_URL}/faces`); if (r.ok) setFaces(await r.json()); } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchFaces(); }, [fetchFaces]);

  const currentPhotoKey = STEPS[step]?.id as "front" | "right" | "left";

  // Webcam — try browser camera first, fallback to backend live feed snapshot
  const openWebcam = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: 640, height: 480 } });
      streamRef.current = s;
      setWebcamActive(true);
      setTimeout(() => { if (videoRef.current) { videoRef.current.srcObject = s; videoRef.current.play(); } }, 100);
    } catch {
      // Fallback: use backend camera snapshot
      showToast({ message: "Using live camera feed for capture", type: "info" });
      setWebcamActive(true);
      // Start polling snapshots from backend into video element via img
      pollBackendCamera();
    }
  };

  const backendSnapshotRef = useRef<HTMLImageElement | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const pollBackendCamera = () => {
    // Poll backend /camera/snapshot every 200ms for live preview
    const poll = async () => {
      try {
        const res = await fetch(`${API_URL}/camera/snapshot`);
        if (res.ok) {
          const data = await res.json();
          if (backendSnapshotRef.current) {
            backendSnapshotRef.current.src = data.image;
          }
        }
      } catch {}
    };
    poll(); // Initial
    pollIntervalRef.current = setInterval(poll, 200);
  };

  const capturePhoto = () => {
    // If using browser webcam
    if (videoRef.current && streamRef.current) {
      const canvas = document.createElement("canvas");
      canvas.width = videoRef.current.videoWidth || 640;
      canvas.height = videoRef.current.videoHeight || 480;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(videoRef.current, 0, 0);
      canvas.toBlob((blob) => {
        if (!blob) return;
        const file = new File([blob], `${currentPhotoKey}-${Date.now()}.jpg`, { type: "image/jpeg" });
        addPhoto(file);
        showToast({ message: "Photo captured!", type: "success" });
      }, "image/jpeg", 0.9);
      return;
    }
    // Fallback: capture from backend snapshot (img element has base64 src)
    const imgSrc = backendSnapshotRef.current?.src;
    if (imgSrc && imgSrc.startsWith("data:image")) {
      try {
        const byteString = atob(imgSrc.split(",")[1]);
        const ab = new ArrayBuffer(byteString.length);
        const ia = new Uint8Array(ab);
        for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i);
        const blob = new Blob([ab], { type: "image/jpeg" });
        const file = new File([blob], `${currentPhotoKey}-${Date.now()}.jpg`, { type: "image/jpeg" });
        addPhoto(file);
        showToast({ message: "Photo captured from live feed!", type: "success" });
      } catch {
        showToast({ message: "Capture failed - try again", type: "error" });
      }
    } else {
      showToast({ message: "No camera feed available", type: "error" });
    }
  };

  const closeWebcam = () => {
    if (streamRef.current) { streamRef.current.getTracks().forEach(t => t.stop()); streamRef.current = null; }
    if (pollIntervalRef.current) { clearInterval(pollIntervalRef.current); pollIntervalRef.current = null; }
    setWebcamActive(false);
  };

  const addPhoto = (file: File) => {
    setPhotos(prev => ({ ...prev, [currentPhotoKey]: [...prev[currentPhotoKey], file] }));
    setPreviews(prev => ({ ...prev, [currentPhotoKey]: [...prev[currentPhotoKey], URL.createObjectURL(file)] }));
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    Array.from(e.target.files).forEach(addPhoto);
    e.target.value = "";
  };

  const removePhoto = (key: "front" | "right" | "left", idx: number) => {
    setPhotos(prev => ({ ...prev, [key]: prev[key].filter((_, i) => i !== idx) }));
    setPreviews(prev => ({ ...prev, [key]: prev[key].filter((_, i) => i !== idx) }));
  };

  const nextStep = () => { closeWebcam(); setStep(s => Math.min(s + 1, STEPS.length - 1)); };
  const prevStep = () => { closeWebcam(); setStep(s => Math.max(s - 1, 0)); };

  const canProceed = () => {
    if (step === 0) return name.trim() && phone.trim();
    if (step === 1) return photos.front.length > 0;
    if (step === 2) return true; // right is optional
    if (step === 3) return true; // left is optional
    return true;
  };

  const handleSubmit = async () => {
    if (!photos.front.length) { showToast({ message: "At least one front photo required", type: "error" }); return; }
    setUploading(true);
    try {
      // Register with first front photo
      const formData = new FormData();
      formData.append("file", photos.front[0]);
      const r = await fetch(`${API_URL}/faces/register?name=${encodeURIComponent(name)}&code=${encodeURIComponent(code)}&phone=${encodeURIComponent(phone)}`, { method: "POST", body: formData });
      if (!r.ok) { const e = await r.json(); showToast(`Failed: ${e.detail}`, "error"); setUploading(false); return; }
      const data = await r.json();

      // Upload additional samples
      const allExtra = [...photos.front.slice(1), ...photos.right, ...photos.left];
      for (const file of allExtra) {
        const sf = new FormData();
        sf.append("file", file);
        await fetch(`${API_URL}/faces/${data.id}/sample`, { method: "POST", body: sf });
      }

      showToast(`${name} registered with ${1 + allExtra.length} photos`, "success");
      resetForm();
      fetchFaces();
    } catch { showToast({ message: "Registration failed", type: "error" }); }
    finally { setUploading(false); }
  };

  const resetForm = () => {
    setStep(0); setName(""); setCode(""); setPhone("");
    setPhotos({ front: [], right: [], left: [] });
    setPreviews({ front: [], right: [], left: [] });
    closeWebcam();
  };

  const handleDelete = async (id: string) => {
    try { await fetch(`${API_URL}/faces/${id}`, { method: "DELETE" }); showToast({ message: "Deleted", type: "success" }); fetchFaces(); } catch {}
  };

  const handleTrain = async () => {
    try { const r = await fetch(`${API_URL}/faces/train`, { method: "POST" }); if (r.ok) showToast({ message: "Sync & Train complete", type: "success" }); } catch { showToast({ message: "Training failed", type: "error" }); }
  };

  if (loading && !faces.length) return <LoadingScreen message="Loading personnel..." />;

  return (
    <div className="min-h-screen p-5 max-w-[1400px] mx-auto animate-fade-in">
      {/* Header */}
      <header className="mb-8 flex justify-between items-center pb-6 border-b" style={{ borderColor: "var(--border)" }}>
        <div>
          <h1 className="text-xl font-bold" style={{ color: "var(--text-main)" }}>Personnel Registry</h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>Manage biometric data for face recognition</p>
        </div>
        <button onClick={handleTrain} className="btn-primary flex items-center gap-2 text-xs">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
          Sync & Train
        </button>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Registration Wizard */}
        <section className="lg:col-span-5">
          <div className="surface-card p-6">
            {/* Step indicator */}
            <div className="flex items-center gap-1 mb-6">
              {STEPS.map((s, i) => (
                <div key={s.id} className="flex items-center gap-1">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold ${i <= step ? "text-white" : ""}`} style={{ background: i <= step ? "var(--accent)" : "var(--bg-input)", color: i <= step ? "white" : "var(--text-faint)" }}>{i + 1}</div>
                  {i < STEPS.length - 1 && <div className="w-4 h-px" style={{ background: i < step ? "var(--accent)" : "var(--border)" }} />}
                </div>
              ))}
            </div>

            <p className="text-xs font-medium mb-4" style={{ color: "var(--text-muted)" }}>{STEPS[step].instruction}</p>

            {/* Step 0: Info */}
            {step === 0 && (
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium mb-1.5 block" style={{ color: "var(--text-muted)" }}>Full Name *</label>
                  <input value={name} onChange={e => setName(e.target.value)} placeholder="John Doe" className="input-field text-sm" />
                </div>
                <div>
                  <label className="text-xs font-medium mb-1.5 block" style={{ color: "var(--text-muted)" }}>Employee ID</label>
                  <input value={code} onChange={e => setCode(e.target.value)} placeholder="EMP-001" className="input-field text-sm" />
                </div>
                <div>
                  <label className="text-xs font-medium mb-1.5 block" style={{ color: "var(--text-muted)" }}>Phone Number *</label>
                  <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="62812345678" className="input-field text-sm" />
                </div>
              </div>
            )}

            {/* Steps 1-3: Photo capture */}
            {(step === 1 || step === 2 || step === 3) && (
              <div className="space-y-4">
                {/* Webcam */}
                {webcamActive && (
                  <div className="rounded-lg overflow-hidden border" style={{ borderColor: "var(--border)" }}>
                    <video ref={videoRef} className="w-full aspect-[4/3] object-cover bg-black" autoPlay muted playsInline style={{ display: streamRef.current ? "block" : "none" }} />
                    <img ref={backendSnapshotRef} className="w-full aspect-[4/3] object-cover bg-black" style={{ display: streamRef.current ? "none" : "block" }} alt="Live feed" />
                    <div className="flex gap-2 p-2" style={{ background: "var(--bg-input)" }}>
                      <button type="button" onClick={capturePhoto} className="btn-primary flex-1 text-xs py-2">Capture</button>
                      <button type="button" onClick={closeWebcam} className="btn-ghost flex-1 text-xs py-2">Done</button>
                    </div>
                  </div>
                )}

                {/* Action buttons */}
                {!webcamActive && (
                  <div className="flex gap-2">
                    <button type="button" onClick={openWebcam} className="btn-ghost flex-1 flex items-center justify-center gap-2 py-3">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                      <span className="text-xs">Take Photo</span>
                    </button>
                    <label className="btn-ghost flex-1 flex items-center justify-center gap-2 py-3 cursor-pointer">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
                      <span className="text-xs">Upload</span>
                      <input type="file" accept="image/*" multiple onChange={handleFileUpload} className="hidden" />
                    </label>
                  </div>
                )}

                {/* Photo grid */}
                {previews[currentPhotoKey].length > 0 && (
                  <div className="grid grid-cols-4 gap-2">
                    {previews[currentPhotoKey].map((url, i) => (
                      <div key={i} className="relative aspect-square rounded-lg overflow-hidden border" style={{ borderColor: "var(--border)" }}>
                        <img src={url} alt={`${currentPhotoKey} ${i+1}`} className="w-full h-full object-cover" />
                        <button onClick={() => removePhoto(currentPhotoKey, i)} className="absolute top-1 right-1 w-5 h-5 rounded-full bg-black/60 text-white flex items-center justify-center text-[10px]">x</button>
                      </div>
                    ))}
                  </div>
                )}

                <p className="text-[11px]" style={{ color: "var(--text-faint)" }}>
                  {previews[currentPhotoKey].length} photo(s) captured. You can add more or proceed.
                </p>
              </div>
            )}

            {/* Step 4: Review */}
            {step === 4 && (
              <div className="space-y-4">
                <div className="p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
                  <p className="text-sm font-medium" style={{ color: "var(--text-main)" }}>{name}</p>
                  <p className="text-xs" style={{ color: "var(--text-faint)" }}>ID: {code || "N/A"} | Phone: {phone}</p>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Front ({photos.front.length})</p>
                    {previews.front[0] && <img src={previews.front[0]} className="w-full aspect-square rounded-lg object-cover border" style={{ borderColor: "var(--border)" }} alt="Front" />}
                  </div>
                  <div>
                    <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Right ({photos.right.length})</p>
                    {previews.right[0] ? <img src={previews.right[0]} className="w-full aspect-square rounded-lg object-cover border" style={{ borderColor: "var(--border)" }} alt="Right" /> : <div className="w-full aspect-square rounded-lg border flex items-center justify-center text-[10px]" style={{ borderColor: "var(--border)", color: "var(--text-faint)" }}>Skip</div>}
                  </div>
                  <div>
                    <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Left ({photos.left.length})</p>
                    {previews.left[0] ? <img src={previews.left[0]} className="w-full aspect-square rounded-lg object-cover border" style={{ borderColor: "var(--border)" }} alt="Left" /> : <div className="w-full aspect-square rounded-lg border flex items-center justify-center text-[10px]" style={{ borderColor: "var(--border)", color: "var(--text-faint)" }}>Skip</div>}
                  </div>
                </div>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>Total: {photos.front.length + photos.right.length + photos.left.length} photos</p>
              </div>
            )}

            {/* Navigation */}
            <div className="flex gap-2 mt-6">
              {step > 0 && <button onClick={prevStep} className="btn-ghost flex-1 py-2.5 text-xs">Back</button>}
              {step < 4 ? (
                <button onClick={nextStep} disabled={!canProceed()} className="btn-primary flex-1 py-2.5 text-xs disabled:opacity-30">
                  {step === 0 ? "Start Photos" : "Next"}
                </button>
              ) : (
                <button onClick={handleSubmit} disabled={uploading} className="btn-primary flex-1 py-2.5 text-xs disabled:opacity-30">
                  {uploading ? "Registering..." : "Register Personnel"}
                </button>
              )}
            </div>
          </div>
        </section>

        {/* Face Directory */}
        <section className="lg:col-span-7">
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-sm font-semibold" style={{ color: "var(--text-main)" }}>Registered ({faces.length})</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {faces.map(face => (
              <div
                key={face.id}
                className="surface-card overflow-hidden group cursor-pointer"
                onClick={() => setSelectedFace(face)}
              >
                <div className="aspect-[4/3] bg-black relative overflow-hidden">
                  <img src={`${API_URL}${face.image_url}`} alt={face.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                  <button
                    onClick={(e) => { e.stopPropagation(); setDeleteModal({ isOpen: true, id: face.id }); }}
                    className="absolute top-2 right-2 w-6 h-6 rounded-full bg-black/60 text-white flex items-center justify-center text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    x
                  </button>
                  <div className="absolute bottom-0 left-0 right-0 p-2 bg-gradient-to-t from-black/70 to-transparent">
                    <span className="text-[9px] font-bold text-white px-1.5 py-0.5 rounded" style={{ background: "var(--accent)" }}>{face.code || "NO ID"}</span>
                  </div>
                </div>
                <div className="p-3">
                  <h3 className="text-sm font-medium truncate" style={{ color: "var(--text-main)" }}>{face.name}</h3>
                  <p className="text-[10px] font-mono" style={{ color: "var(--text-faint)" }}>{new Date(face.registered_at).toLocaleDateString()}</p>
                </div>
              </div>
            ))}
            {!faces.length && (
              <div className="col-span-full py-16 text-center">
                <p className="text-sm" style={{ color: "var(--text-faint)" }}>No personnel registered</p>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* Personnel Detail Overlay */}
      <DetailPanel
        isOpen={!!selectedFace}
        onClose={() => setSelectedFace(null)}
        title="Personnel Detail"
        width="460px"
      >
        {selectedFace && (
          <div>
            {/* Main photo - large */}
            <div className="mb-4 rounded-xl overflow-hidden border" style={{ borderColor: "var(--border)" }}>
              <img
                src={`${API_URL}${selectedFace.image_url}`}
                alt={selectedFace.name}
                className="w-full max-h-[280px] object-contain bg-black"
              />
            </div>

            {/* Info grid / Edit form */}
            <div className="space-y-3 mb-4">
              <div className="p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
                <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Full Name</p>
                {editMode ? (
                  <input value={editName} onChange={e => setEditName(e.target.value)} className="input-field text-sm" />
                ) : (
                  <p className="text-sm font-semibold" style={{ color: "var(--text-main)" }}>{selectedFace.name}</p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
                  <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Employee ID</p>
                  {editMode ? (
                    <input value={editCode} onChange={e => setEditCode(e.target.value)} className="input-field text-sm font-mono" />
                  ) : (
                    <p className="text-sm font-semibold font-mono" style={{ color: "var(--text-main)" }}>{selectedFace.code || "N/A"}</p>
                  )}
                </div>
                <div className="p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
                  <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Phone</p>
                  {editMode ? (
                    <input value={editPhone} onChange={e => setEditPhone(e.target.value)} className="input-field text-sm" />
                  ) : (
                    <p className="text-sm font-semibold" style={{ color: "var(--text-main)" }}>{selectedFace.phone || "N/A"}</p>
                  )}
                </div>
              </div>

              <div className="p-3 rounded-lg" style={{ background: "var(--bg-input)" }}>
                <p className="text-[10px] font-medium mb-1" style={{ color: "var(--text-faint)" }}>Registration Date</p>
                <p className="text-sm" style={{ color: "var(--text-main)" }}>{new Date(selectedFace.registered_at).toLocaleString()}</p>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-3">
              {editMode ? (
                <>
                  <button onClick={() => setEditMode(false)} className="flex-1 py-2.5 rounded-lg text-sm font-medium transition-all" style={{ background: "var(--bg-input)", border: "1px solid var(--border)", color: "var(--text-muted)" }}>Cancel</button>
                  <button
                    onClick={async () => {
                      setSavingEdit(true);
                      try {
                        const params = new URLSearchParams();
                        if (editName) params.set("name", editName);
                        if (editCode) params.set("code", editCode);
                        if (editPhone) params.set("phone", editPhone);
                        const r = await fetch(`${API_URL}/faces/${selectedFace.id}?${params}`, { method: "PUT" });
                        if (r.ok) { showToast({ message: "Personnel updated", type: "success" }); fetchFaces(); setSelectedFace(null); setEditMode(false); }
                        else showToast({ message: "Update failed", type: "error" });
                      } catch { showToast({ message: "Update failed", type: "error" }); }
                      finally { setSavingEdit(false); }
                    }}
                    disabled={savingEdit}
                    className="flex-1 py-2.5 rounded-lg text-sm font-medium text-white transition-all disabled:opacity-30"
                    style={{ background: "var(--accent)" }}
                  >
                    {savingEdit ? "Saving..." : "Save"}
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => { setSelectedFace(null); setDeleteModal({ isOpen: true, id: selectedFace.id }); }}
                    className="py-2.5 px-4 rounded-lg text-sm font-medium transition-all border border-red-500/20 text-red-400 hover:bg-red-500/10"
                  >
                    Delete
                  </button>
                  <button
                    onClick={() => { setEditMode(true); setEditName(selectedFace.name); setEditCode(selectedFace.code || ""); setEditPhone(selectedFace.phone || ""); }}
                    className="flex-1 py-2.5 rounded-lg text-sm font-medium text-white transition-all"
                    style={{ background: "var(--accent)" }}
                  >
                    Edit
                  </button>
                </>
              )}
            </div>
          </div>
        )}
      </DetailPanel>

      <Modal isOpen={deleteModal.isOpen} onClose={() => setDeleteModal({ isOpen: false, id: null })} onConfirm={() => deleteModal.id && handleDelete(deleteModal.id)} title="Delete Face Data" message="This will permanently remove this person from the recognition database." confirmText="Delete" cancelText="Cancel" type="danger" />
    </div>
  );
}
