import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Generativa",
  description: "Suite de IA generativa local",
};

/** Marco de foto + destello: el mismo trazo que icon.svg (pestaña del navegador). */
function LogoMark() {
  return (
    <svg width="20" height="20" viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="navLogo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5b8def" />
          <stop offset="1" stopColor="#9b6bef" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="7" fill="url(#navLogo)" />
      <rect x="6" y="8.5" width="20" height="15" rx="2.5" fill="none" stroke="#ffffff" strokeWidth="1.8" />
      <circle cx="11.5" cy="13" r="1.8" fill="#ffffff" />
      <path d="M7 21.5l5.2-5.4 3.6 3.7 3.4-3.9L25 21.5z" fill="#ffffff" />
      <path d="M23.5 5.2l.85 2.45 2.45.85-2.45.85-.85 2.45-.85-2.45L20.2 8.5l2.45-.85z" fill="#ffffff" />
    </svg>
  );
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>
        <nav
          style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            flexShrink: 0,
            padding: "12px 24px",
            borderBottom: "1px solid #2a2e37",
            background: "#0f1115",
          }}
        >
          <span style={{ display: "flex", alignItems: "center", gap: 8, marginRight: 8 }}>
            <LogoMark />
            <span style={{ color: "#f2f2f2", fontWeight: 700, fontSize: 14 }}>Generativa</span>
          </span>
          <Link href="/" style={{ color: "#f2f2f2", fontWeight: 600, fontSize: 14 }}>
            Chat
          </Link>
          <Link href="/imagenes" style={{ color: "#f2f2f2", fontWeight: 600, fontSize: 14 }}>
            Imágenes
          </Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
