import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import ToastContainer from "@/components/Toast";
import ThemeProvider from "@/components/ThemeProvider";

export const metadata: Metadata = {
  title: "SIEWS+ — Smart Integrated Early Warning System",
  description: "AI-powered safety monitoring for upstream oil & gas facilities.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
        <script dangerouslySetInnerHTML={{ __html: `(function(){try{var t=localStorage.getItem('siews-theme')||'dark';document.documentElement.setAttribute('data-theme',t)}catch(e){}})()` }} />
      </head>
      <body className="min-h-screen antialiased">
        <ThemeProvider>
          <Navbar />
          <main className="pt-[76px]">{children}</main>
          <ToastContainer />
        </ThemeProvider>
      </body>
    </html>
  );
}
