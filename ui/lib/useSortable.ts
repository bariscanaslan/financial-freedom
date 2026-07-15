"use client";

import { useMemo, useState } from "react";

export type SortDirection = "asc" | "desc";
export type SortValue = string | number | boolean | null | undefined;

export function useSortable<T>(
  rows: T[],
  fields: Record<string, (row: T) => SortValue>,
  initialKey: string,
) {
  const [key, setKey] = useState(initialKey);
  const [direction, setDirection] = useState<SortDirection>("asc");
  const sorted = useMemo(() => [...rows].sort((a, b) => {
    const av = fields[key](a);
    const bv = fields[key](b);
    if (av == null) return 1;
    if (bv == null) return -1;
    const result = typeof av === "number" && typeof bv === "number"
      ? av - bv
      : String(av).localeCompare(String(bv), "tr");
    return direction === "asc" ? result : -result;
  }), [rows, fields, key, direction]);

  function sort(nextKey: string) {
    if (nextKey === key) setDirection((value) => value === "asc" ? "desc" : "asc");
    else { setKey(nextKey); setDirection("asc"); }
  }
  return { sorted, sort, key, direction };
}
