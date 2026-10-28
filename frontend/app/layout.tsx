import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Fleet overview · Device Health", template: "%s · Device Health" },
  description: "Investigate simulated device health, current telemetry, and reading history.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>
    <a href="#main-content" className="skip-link">Skip to content</a>
    <header className="app-header"><div className="header-inner">
      <Link href="/" className="brand" aria-label="Device Health fleet overview">
        <span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" width="22" height="22" fill="none">
          <rect x="5" y="5" width="14" height="14" rx="3" stroke="currentColor" strokeWidth="1.4" />
          <path d="M8 12h2l1.5-3 2 6 1.5-3h1M9 2v3m6-3v3M9 19v3m6-3v3M2 9h3m-3 6h3m14-6h3m-3 6h3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg></span><span>Device Health<span className="brand-subtitle">Fleet monitoring</span></span>
      </Link>
      <div className="header-right"><Link href="/" className="nav-link">Fleet overview</Link>
        <span className="simulation-badge"><span aria-hidden="true" />Simulated data</span></div>
    </div></header>
    <main id="main-content" className="app-main">{children}</main>
    <footer className="app-footer"><span>Device Health &amp; Predictive Maintenance</span>
      <span>Simulator telemetry · Times shown in UTC</span></footer>
  </body></html>;
}
