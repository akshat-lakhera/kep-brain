import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <div className="mx-auto max-w-[60ch] space-y-4 py-10">
      <p className="font-mono text-xs text-fg-muted">404</p>
      <h1 className="text-xl font-semibold">This page does not exist</h1>
      <p className="text-fg-secondary">
        The address may be mistyped, or it points at a KEP, person or SIG that is not in the graph. KEP pages live under{" "}
        <span className="font-mono">/explore/kep/&lt;number&gt;</span>, people under{" "}
        <span className="font-mono">/explore/person/&lt;login&gt;</span> and SIGs under{" "}
        <span className="font-mono">/explore/sig/&lt;key&gt;</span>.
      </p>
      <ul className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
        <li>
          <Link href="/ask" className="quiet-link">
            Ask a question
          </Link>
        </li>
        <li>
          <Link href="/explore" className="quiet-link">
            Explore KEPs, SIGs and people
          </Link>
        </li>
        <li>
          <Link href="/audit" className="quiet-link">
            Open the audit
          </Link>
        </li>
      </ul>
    </div>
  );
}
