"use client";

import Link from "next/link";
import Image from "next/image";

export default function HomePage() {
  const features = [
    { title: "Helmet Detection", desc: "Automatic hard hat compliance monitoring" },
    { title: "Vest Detection", desc: "Real-time safety vest verification" },
    { title: "Zone Violation", desc: "Restricted area intrusion alerts" },
    { title: "Fire & Smoke", desc: "Early fire and smoke detection" },
    { title: "Face Recognition", desc: "Automated personnel identification" },
    { title: "Road Damage", desc: "Pothole and road hazard detection" },
  ];

  const steps = [
    { num: "01", title: "CCTV Camera", desc: "Cameras installed at work areas" },
    { num: "02", title: "AI Analysis", desc: "YOLO model processes every frame" },
    { num: "03", title: "Detection", desc: "Violations identified in real-time" },
    { num: "04", title: "Alert", desc: "WhatsApp & dashboard notifications" },
  ];

  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <section className="relative min-h-[85vh] flex items-center justify-center px-6 overflow-hidden">
        {/* Animated gradient background */}
        <div className="absolute inset-0 animate-gradient bg-gradient-to-br from-[var(--accent-dark)]/8 via-transparent to-[var(--accent)]/5" />
        {/* Slow-moving orbs */}
        <div className="absolute top-1/4 left-1/4 w-[400px] h-[400px] bg-[var(--accent)]/[0.03] rounded-full blur-[80px] animate-pulse" style={{ animationDuration: "6s" }} />
        <div className="absolute bottom-1/4 right-1/4 w-[300px] h-[300px] bg-[var(--accent-light)]/[0.03] rounded-full blur-[60px] animate-pulse" style={{ animationDuration: "8s", animationDelay: "2s" }} />
        {/* Grid pattern overlay */}
        <div className="absolute inset-0 opacity-[0.02]" style={{ backgroundImage: "radial-gradient(circle, var(--text-main) 1px, transparent 1px)", backgroundSize: "40px 40px" }} />

        <div className="relative z-10 max-w-4xl mx-auto text-center">
          <div className="flex justify-center mb-8">
            <Image src="/logo-siews.png" alt="SIEWS+" width={72} height={72} priority />
          </div>

          <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold text-[var(--text-main)] leading-tight mb-6">
            AI-Powered{" "}
            <span className="text-[var(--accent-light)]">PPE Detection</span>
            <br />
            for Industrial Safety
          </h1>

          <p className="text-base text-[var(--text-muted)] max-w-2xl mx-auto mb-10 leading-relaxed">
            Smart monitoring system powered by AI that detects PPE usage, zone violations,
            and environmental hazards in real-time at oil & gas facilities.
          </p>

          <div className="flex items-center justify-center gap-4 flex-wrap">
            <Link
              href="/dashboard"
              className="px-8 py-3.5 bg-[var(--accent)] text-white rounded-xl font-semibold text-sm hover:bg-[var(--accent-light)] transition-all shadow-lg shadow-[var(--accent)]/20"
            >
              Open Dashboard
            </Link>
            <Link
              href="/settings"
              className="px-8 py-3.5 bg-[var(--border)] text-[var(--text-muted)] rounded-xl font-semibold text-sm border border-[var(--border-bright)] hover:bg-[var(--border-bright)] hover:text-[var(--text-main)] transition-all"
            >
              Settings
            </Link>
          </div>
        </div>
      </section>

      {/* How it Works */}
      <section className="py-20 px-6">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl font-bold text-[var(--text-main)] text-center mb-3">How it Works</h2>
          <p className="text-[var(--text-faint)] text-center mb-14 text-sm">From camera to alert in seconds</p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {steps.map((step) => (
              <div key={step.num} className="text-center group">
                <div className="w-12 h-12 rounded-xl bg-[var(--accent)]/10 border border-[var(--accent)]/15 flex items-center justify-center mx-auto mb-4 group-hover:bg-[var(--accent)]/20 transition-all">
                  <span className="text-[var(--accent-light)] font-bold text-base font-mono">{step.num}</span>
                </div>
                <h3 className="text-[var(--text-main)] font-semibold text-sm mb-1">{step.title}</h3>
                <p className="text-[var(--text-faint)] text-xs">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Detection Modules */}
      <section className="py-20 px-6 border-t border-[var(--border)]">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-2xl font-bold text-[var(--text-main)] text-center mb-3">Detection Modules</h2>
          <p className="text-[var(--text-faint)] text-center mb-14 text-sm">AI models trained for various safety scenarios</p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {features.map((f) => (
              <div
                key={f.title}
                className="p-5 rounded-2xl bg-[var(--bg-surface)] border border-[var(--border)] hover:border-[var(--accent)]/20 transition-all group"
              >
                <svg className="w-5 h-5 text-[var(--accent-light)] mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <h3 className="text-[var(--text-main)] font-semibold text-sm mb-1">{f.title}</h3>
                <p className="text-[var(--text-faint)] text-xs leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-6 border-t border-[var(--border)]">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-2xl md:text-3xl font-bold text-[var(--text-main)] mb-4">
            100% PPE Compliance — Every Shift, Every Site
          </h2>
          <p className="text-[var(--text-faint)] mb-8 text-sm">Ensure workplace safety with 24/7 AI monitoring</p>
          <Link
            href="/dashboard"
            className="inline-block px-8 py-3.5 bg-[var(--accent)] text-white rounded-xl font-semibold text-sm hover:bg-[var(--accent-light)] transition-all shadow-lg shadow-[var(--accent)]/20"
          >
            Start Monitoring
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-6 border-t border-[var(--border)]">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Image src="/logo-siews.png" alt="SIEWS+" width={22} height={22} />
            <span className="text-sm text-[var(--text-faint)]">SIEWS+ v5.0</span>
          </div>
          <p className="text-xs text-[var(--text-faint)]">Smart Integrated Early Warning System</p>
        </div>
      </footer>
    </div>
  );
}
