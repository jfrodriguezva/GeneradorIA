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

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>
        <nav
          style={{
            display: "flex",
            gap: 16,
            padding: "12px 24px",
            borderBottom: "1px solid #2a2e37",
            background: "#0f1115",
          }}
        >
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
