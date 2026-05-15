"use client";

interface ToastOptions {
  message: string;
  type?: "success" | "error" | "info";
  duration?: number;
}

export function showToast({ message, type = "info", duration = 3000 }: ToastOptions) {
  const colors = {
    success: "bg-emerald-500/90",
    error: "bg-red-500/90",
    info: "bg-blue-500/90",
  };

  const toast = document.createElement("div");
  toast.className = `fixed top-4 right-4 z-[200] px-4 py-3 rounded-lg text-white text-xs font-medium shadow-lg ${colors[type]} animate-fade-in`;
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

export default function ToastContainer() {
  return null; // Toasts are rendered via DOM manipulation in showToast
}
