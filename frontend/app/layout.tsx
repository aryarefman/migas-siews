import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "SIEWS+ 5.0 — Smart Integrated Early Warning System",
  description:
    "AI-Based Human Presence Detection for Intelligent Safety Shutdown in upstream oil & gas facilities. Real-time monitoring, zone violation detection, and automated safety response.",
  keywords: "safety, oil gas, AI detection, YOLO, shutdown system, monitoring",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
      </head>
      <body className="min-h-screen bg-[#0a0e17] text-slate-200 antialiased">
        <Navbar />
        <main className="pt-[72px]">{children}</main>
      </body>
    </html>
  );
}
