import type { SortDirection } from "@/lib/useSortable";

export function SortHeader({
  label, column, active, direction, onSort, left = false,
}: {
  label: string; column: string; active: boolean; direction: SortDirection;
  onSort: (column: string) => void; left?: boolean;
}) {
  return (
    <th scope="col" className={left ? "left" : undefined} aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}>
      <button className="sort-button" onClick={() => onSort(column)}>
        {label}<span aria-hidden="true">{active ? (direction === "asc" ? " ↑" : " ↓") : " ↕"}</span>
      </button>
    </th>
  );
}
