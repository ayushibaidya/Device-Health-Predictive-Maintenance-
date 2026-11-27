"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export function MainNav() {
  const path = usePathname();
  return <nav className="main-nav" aria-label="Main navigation">
    <Link href="/" className="nav-link" aria-current={path === "/" || path.startsWith("/devices/") ? "page" : undefined}>Fleet overview</Link>
    <Link href="/alerts" className="nav-link" aria-current={path.startsWith("/alerts") ? "page" : undefined}>Alerts</Link>
  </nav>;
}
