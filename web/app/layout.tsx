/**
 * The Adensa Digital application shell: a professional
 * operational navigation frame around the product surfaces.
 * Streamlit-free by design — this is the production-style
 * client consuming the /v1 API boundary (ADR-011).
 *
 * P8.1 foundations: Inter via next/font (self-hosted at build
 * time, exposed as the --font-inter variable the type scale
 * consumes), an accessible skip link to the main content, and
 * the primary navigation with an active-page treatment.
 */

import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AppNav } from "@/components/AppNav";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Adensa Digital — Operational Control Tower",
  description:
    "Supply-chain exception detection, decision support and recovery workflow.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <a className="skip-link" href="#main-content">
          Skip to main content
        </a>
        <div className="app-shell">
          <header className="app-header">
            <div className="app-brand">
              <span className="app-brand-name">Adensa Digital</span>
              <span className="app-brand-sub">Supply-chain operations</span>
            </div>
            <nav aria-label="Primary">
              <AppNav />
            </nav>
          </header>
          <main className="app-main" id="main-content">
            {children}
          </main>
          <footer className="app-footer">
            Adensa Digital — operational decision support. Recommendations are
            decision support; planners approve every recovery.
          </footer>
        </div>
      </body>
    </html>
  );
}
