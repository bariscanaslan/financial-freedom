"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useCurrency } from "./CurrencyProvider";

const LINKS = [
  { href: "/", label: "Genel Bakış" },
  { href: "/portfolio", label: "Portföy" },
  { href: "/portfolio-builder", label: "Portföy Oluştur" },
  { href: "/portfolio-reports", label: "Portföy Raporları" },
  { href: "/predict", label: "Tahmin" },
  { href: "/predictions", label: "Tahminler" },
  { href: "/train", label: "Model Eğitimi" },
  { href: "/risk", label: "Risk" },
  { href: "/risks", label: "Riskler" },
  { href: "/guide", label: "Rehber" },
];

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [, setClock] = useState(0);
  const { currency, rate, asOf, loading, toggle } = useCurrency();
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => { const timer = window.setInterval(() => setClock((value) => value + 1), 60_000); return () => window.clearInterval(timer); }, []);
  const relativeUpdate = (() => {
    if (!asOf) return "Güncelleme bekleniyor";
    const minutes = Math.max(0, Math.floor((Date.now() - new Date(asOf).getTime()) / 60_000));
    if (minutes < 1) return "az önce";
    if (minutes < 60) return `${minutes} dk önce`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} sa önce`;
    return `${Math.floor(hours / 24)} gün önce`;
  })();
  return (
    <nav className="nav" aria-label="Ana menü">
      <div className="nav-shell">
      <Link className="brand" href="/" aria-label="Financial Freedom ana sayfa">
        <span className="brand-mark" aria-hidden="true">F</span>
        <span><strong>Financial</strong><small>Freedom</small></span>
      </Link>
      <button className="nav-toggle" type="button" aria-expanded={open} aria-controls="main-navigation" onClick={() => setOpen((value) => !value)}>
        <span className="sr-only">Menüyü aç veya kapat</span>
        <span aria-hidden="true"></span><span aria-hidden="true"></span><span aria-hidden="true"></span>
      </button>
      <button className="currency-toggle" type="button" onClick={toggle} disabled={loading || !rate} title={rate ? `1 USD = ${rate.toFixed(4)} TRY · ${asOf}` : "Kur yükleniyor"}>
        <span>{currency} <b>↔</b> {currency === "USD" ? "TRY" : "USD"}</span>
        {rate ? <small>1 USD = {rate.toFixed(2)} TRY<br />1 TRY = {(1 / rate).toFixed(4)} USD<br /><em>Güncelleme: {relativeUpdate}</em></small> : <small>Kur yükleniyor…</small>}
      </button>
      <ul id="main-navigation" className={open ? "is-open" : ""}> 
        {LINKS.map((l) => {
          const active = l.href === "/"
            ? pathname === "/"
            : pathname === l.href || pathname.startsWith(`${l.href}/`);
          return (
            <li key={l.href}>
              <Link href={l.href} aria-current={active ? "page" : undefined}>
                {l.label}
              </Link>
            </li>
          );
        })}
      </ul>
      </div>
    </nav>
  );
}
