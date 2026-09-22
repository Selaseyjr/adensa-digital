/**
 * The Adensa Digital application shell: a professional
 * operational navigation frame around the product surfaces.
 * Streamlit-free by design — this is the production-style
 * client consuming the /v1 API boundary (ADR-011).
 */

import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Adensa Digital — Operational Control Tower",
  description:
    "Supply-chain exception detection, decision support and recovery workflow.",
};

const NAV_ITEMS = [
  { href: "/", label: "Control Tower" },
  { href: "/exceptions", label: "Exceptions" },
  { href: "/operations", label: "Operations" },
  { href: "/administration", label: "Administration" },
] as const;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <header className="app-header">
            <div className="app-brand">
              <span className="app-brand-name">Adensa Digital</span>
              <span className="app-brand-sub">Supply-chain operations</span>
            </div>
            <nav aria-label="Primary">
              <ul className="app-nav">
                {NAV_ITEMS.map((item) => (
                  <li key={item.href}>
                    <Link href={item.href}>{item.label}</Link>
                  </li>
                ))}
              </ul>
            </nav>
          </header>
          <main className="app-main">{children}</main>
          <footer className="app-footer">
            Adensa Digital — operational decision support. Recommendations are
            decision support; planners approve every recovery.
          </footer>
        </div>
      </body>
    </html>
  );
}
