"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { getUsdTryRate } from "@/lib/api";
import { configureMoney } from "@/lib/format";

type CurrencyState = { currency: "USD" | "TRY"; rate: number | null; asOf: string | null;
  loading: boolean; toggle: () => void };
const CurrencyContext = createContext<CurrencyState>({ currency: "USD", rate: null, asOf: null, loading: true, toggle: () => undefined });

export function CurrencyProvider({ children }: { children: React.ReactNode }) {
  const [currency, setCurrency] = useState<"USD" | "TRY">("USD");
  const [rate, setRate] = useState<number | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    const load = () => getUsdTryRate().then((data) => {
      if (!active) return;
      const preferred = localStorage.getItem("display-currency") === "TRY" ? "TRY" : "USD";
      configureMoney(preferred, data.rate); setRate(data.rate); setAsOf(data.as_of); setCurrency(preferred);
    }).finally(() => { if (active) setLoading(false); });
    load();
    const timer = window.setInterval(load, 15 * 60 * 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);
  function toggle() {
    if (!rate) return;
    const next = currency === "USD" ? "TRY" : "USD";
    configureMoney(next, rate); localStorage.setItem("display-currency", next); setCurrency(next);
  }
  return <CurrencyContext.Provider value={{ currency, rate, asOf, loading, toggle }}>
    <div className="app-shell" key={`${currency}-${rate}`}>{children}</div>
  </CurrencyContext.Provider>;
}
export const useCurrency = () => useContext(CurrencyContext);
