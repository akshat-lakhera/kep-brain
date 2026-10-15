import Link from "next/link";
import type { Route } from "next";
import type { ReactNode } from "react";

/** A GitHub login as an identifier: mono, with @, linked to its Person page (05 §5.3). */
export function PersonLink({ login, className }: { login: string; className?: string }) {
  return (
    <Link href={`/explore/person/${encodeURIComponent(login)}` as Route} className={className ?? "quiet-link ident"}>
      @{login}
    </Link>
  );
}

/** A SIG as its directory name in mono, linked to its SIG page. */
export function SigLink({ sig, children, className }: { sig: string; children?: ReactNode; className?: string }) {
  return (
    <Link href={`/explore/sig/${encodeURIComponent(sig)}` as Route} className={className ?? "quiet-link font-mono"}>
      {children ?? sig}
    </Link>
  );
}

export function PersonList({ people }: { people: { login: string }[] }) {
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-1">
      {people.map((p) => (
        <PersonLink key={p.login} login={p.login} />
      ))}
    </span>
  );
}
