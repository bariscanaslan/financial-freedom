"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useCurrency } from "./CurrencyProvider";

const LINKS = [
  { href: "/", label: "Genel Bakış" },
];

const SECONDARY_LINKS = [
  { href: "/train", label: "Model Eğitimi" },
  { href: "/guide", label: "Rehber" },
];

const GROUPS = [
  { label: "Portföy", links: [
    { href: "/portfolio", label: "Portföyler" },
    { href: "/portfolio-builder", label: "Portföy Oluştur" },
    { href: "/portfolio-reports", label: "Portföy Raporları" },
  ] },
  { label: "Tahmin", links: [
    { href: "/predict", label: "Tahmin Oluştur" },
    { href: "/predictions", label: "Kayıtlı Tahminler" },
  ] },
  { label: "Risk", links: [
    { href: "/risk", label: "Risk Analizi" },
    { href: "/risks", label: "Kayıtlı Riskler" },
  ] },
  { label: "Bildirimler", links: [
    { href: "/watchlist", label: "Takip Listesi" },
    { href: "/settings", label: "Ayarlar" },
  ] },
];

export function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [clockTick, setClock] = useState(0);
  const { currency, rate, asOf, loading, toggle } = useCurrency();
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => { const timer = window.setInterval(() => setClock((value) => value + 1), 1_000); return () => window.clearInterval(timer); }, []);
  const clock = (timeZone: string) => clockTick === 0 ? "--:--:--" : new Intl.DateTimeFormat("tr-TR", {
    timeZone, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(new Date());
  const relativeUpdate = (() => {
    if (!asOf) return "Güncelleme bekleniyor";
    const minutes = Math.max(0, Math.floor((Date.now() - new Date(asOf).getTime()) / 60_000));
    if (minutes < 1) return "az önce";
    if (minutes < 60) return `${minutes} dk önce`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} sa önce`;
    return `${Math.floor(hours / 24)} gün önce`;
  })();
  const isActive = (href: string) => href === "/"
    ? pathname === "/"
    : pathname === href || pathname.startsWith(`${href}/`);
  return (
    <nav className="nav" aria-label="Ana menü">
      <div className="nav-shell">
      <Link className="brand" href="/" aria-label="Financial Freedom ana sayfa">
        <span className="brand-mark" aria-hidden="true">
          <Image src="/favicon.svg" alt="" width={38} height={38} priority />
        </span>
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
      <div className="clock-panel">
        <div className="market-clocks" aria-label="Türkiye ve Amerika canlı saatleri">
          <div><span>TR</span><strong>{clock("Europe/Istanbul")}</strong><small>İstanbul</small></div>
          <div><span>US</span><strong>{clock("America/New_York")}</strong><small>New York</small></div>
        </div>
        <small className="market-close-note">US normal seans kapanışı: 16:00</small>
      </div>
      <ul id="main-navigation" className={`nav-menu${open ? " is-open" : ""}`}>
        {LINKS.map((l) => {
          const active = isActive(l.href);
          return (
            <li key={l.href}>
              <Link href={l.href} aria-current={active ? "page" : undefined}>
                {l.label}
              </Link>
            </li>
          );
        })}
        {GROUPS.map((group) => {
          const active = group.links.some((link) => isActive(link.href));
          return (
            <li className="nav-dropdown" key={group.label}>
              <details>
                <summary className={active ? "is-active" : undefined}>{group.label}</summary>
                <ul className="nav-dropdown-menu">
                  {group.links.map((link) => (
                    <li key={link.href}>
                      <Link href={link.href} aria-current={isActive(link.href) ? "page" : undefined}>
                        {link.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          );
        })}
        {SECONDARY_LINKS.map((link) => (
          <li key={link.href}>
            <Link href={link.href} aria-current={isActive(link.href) ? "page" : undefined}>
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
      </div>
    </nav>
  );
}
