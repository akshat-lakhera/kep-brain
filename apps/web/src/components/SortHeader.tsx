import type { ReactNode } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { cx, thClass } from "@/components/ui";

/** A sortable column header: a button inside a `<th>` that carries `aria-sort` for the active column. */
export function SortHeader({
  active,
  dir,
  onClick,
  children,
  className,
  buttonClassName,
}: {
  active: boolean;
  dir: 1 | -1;
  onClick: () => void;
  children: ReactNode;
  className?: string;
  buttonClassName?: string;
}) {
  return (
    <th className={cx(thClass, className)} aria-sort={active ? (dir === 1 ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        onClick={onClick}
        className={cx("inline-flex items-center gap-1", active ? "text-fg" : "hover:text-fg", buttonClassName)}
      >
        {children}
        {active ? (
          dir === 1 ? (
            <ArrowUp aria-hidden="true" size={12} strokeWidth={1.5} />
          ) : (
            <ArrowDown aria-hidden="true" size={12} strokeWidth={1.5} />
          )
        ) : null}
      </button>
    </th>
  );
}
