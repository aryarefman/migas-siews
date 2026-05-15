"use client";

interface SnapshotModalProps {
  isOpen: boolean;
  onClose: () => void;
  imageUrl: string;
  title?: string;
}

export default function SnapshotModal({ isOpen, onClose, imageUrl, title }: SnapshotModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm" onClick={onClose}>
      <div className="relative max-w-4xl max-h-[90vh] p-2" onClick={(e) => e.stopPropagation()}>
        {title && <p className="text-xs text-industrial-400 mb-2 text-center">{title}</p>}
        <img src={imageUrl} alt="Snapshot" className="max-w-full max-h-[85vh] rounded-lg object-contain" />
        <button
          onClick={onClose}
          className="absolute top-0 right-0 w-8 h-8 rounded-full bg-black/60 text-white flex items-center justify-center text-sm hover:bg-black/80 transition-all"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
