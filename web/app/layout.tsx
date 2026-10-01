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
 *
 * Visual Identity v1: the brand mark renders as a component
 * (web/components/brand/BrandMark.tsx) in the header lockup
 * and the footer brand line; the theme init script applies
 * the persisted light/dark Command Centre choice before first
 * paint so the environment never flashes.
 */

import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AppNav } from "@/components/AppNav";
import { BrandMark } from "@/components/brand/BrandMark";
import { ThemeToggle } from "@/components/ThemeToggle";

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

/**
 * Runs before first paint: restores the persisted environment
 * (light workspace / dark Command Centre) from localStorage.
 * Kept tiny and dependency-free; localStorage access is guarded
 * for private-mode contexts, defaulting to the light workspace.
 */
const themeInitScript = `(function(){try{var t=localStorage.getItem("adensa-theme");if(t==="dark"){document.documentElement.dataset.theme="dark";}}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <a className="skip-link" href="#main-content">
          Skip to main content
        </a>
        <div className="app-shell">
          <header className="app-header">
            <div className="app-brand">
              <BrandMark size={30} decorative />
              <span className="app-brand-name">Adensa Digital</span>
              <span className="app-brand-sub">Supply-chain operations</span>
            </div>
            <div className="app-header-end">
              <nav aria-label="Primary">
                <AppNav />
              </nav>
              <ThemeToggle />
            </div>
          </header>
          <main className="app-main" id="main-content">
            {children}
          </main>
          <footer className="app-footer">
            <div className="app-footer-brand">
              <BrandMark size={18} decorative />
            </div>
            Adensa Digital — operational decision support. Recommendations are
            decision support; planners approve every recovery.
          </footer>
        </div>
      </body>
    </html>
  );
}
