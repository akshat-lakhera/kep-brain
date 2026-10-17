import type { Route } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { ArrowDown, ArrowRight } from "lucide-react";
import { serverApi } from "@/lib/api/server";
import type { FindingsSummary, Meta } from "@/lib/api/types";
import { cx } from "@/components/ui";

/** The product's front door: the mark, one sentence, one button. Everything below the fold explains it. */
export default function LandingPage() {
  // The hero needs no data; the live numbers stream in behind it so the route can be prerendered.
  return (
    <Suspense fallback={<Landing graph={null} sigs={[]} summary={null} />}>
      <LiveLanding />
    </Suspense>
  );
}

async function LiveLanding() {
  const [meta, findings] = await Promise.all([serverApi.meta(), serverApi.findings({})]);
  return (
    <Landing
      graph={meta.ok ? meta.data.graph : null}
      sigs={meta.ok ? meta.data.sigs : []}
      summary={findings.ok ? findings.data.summary : null}
    />
  );
}

function Landing({ graph, sigs, summary }: { graph: Meta["graph"] | null; sigs: string[]; summary: FindingsSummary | null }) {
  const fmt = (n: number) => n.toLocaleString("en-US");

  return (
    <div className="-mx-4 -my-6 md:-mx-6">
      <section className="relative flex min-h-[calc(100vh-3rem)] flex-col items-center justify-center px-6 text-center">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top,_var(--c-accent-subtle),_transparent_60%)]"
        />
        <Mark className="h-20 w-20 md:h-24 md:w-24" />
        <h1 className="display mt-8 text-[40px] font-semibold md:text-[64px]">KEP Brain</h1>
        <p className="mt-5 max-w-[34ch] text-md text-fg-secondary md:text-lg">
          The decision record of Kubernetes in one graph: who decided, on what evidence, and where the records disagree.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            href={"/ask" as Route}
            className="inline-flex h-11 items-center gap-2 rounded-md bg-accent px-5 text-md font-medium text-on-accent hover:bg-accent-hover"
          >
            Open KEP Brain
            <ArrowRight aria-hidden="true" size={16} strokeWidth={2} />
          </Link>
          <Link
            href="/audit"
            className="inline-flex h-11 items-center rounded-md border border-border-strong px-5 text-md font-medium hover:bg-surface"
          >
            See the audit
          </Link>
        </div>
        {graph ? (
          <p className="eyebrow mt-10 flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
            <span>{fmt(graph.keps)} KEPs</span>
            <Dot />
            <span>{fmt(graph.people)} people</span>
            <Dot />
            <span>{fmt(graph.findings)} records that disagree</span>
            {sigs.length ? (
              <>
                <Dot />
                <span className="font-mono normal-case tracking-normal">{sigs.join(" · ")}</span>
              </>
            ) : null}
          </p>
        ) : null}
        <a
          href="#problem"
          className="absolute bottom-6 inline-flex flex-col items-center gap-1 text-xs text-fg-muted hover:text-fg"
          aria-label="Read how it works"
        >
          <span>What it does</span>
          <ArrowDown aria-hidden="true" size={14} strokeWidth={1.5} />
        </a>
      </section>

      <Section id="problem" eyebrow="The problem" title="A KEP's state is written in four places. Nothing keeps them in step.">
        <div className="grid gap-8 md:grid-cols-2">
          <p className="text-md text-fg-secondary">
            Every significant change to Kubernetes goes through a KEP, a Kubernetes Enhancement Proposal. Its state lives in the
            kep.yaml file, in the tracking issue&apos;s state, labels and milestone, in the pull requests that changed it, and in the
            KEPs it replaces or is replaced by. Different people write those records at different times.
          </p>
          <p className="text-md text-fg-secondary">
            They drift apart, and the drift is invisible to anyone reading one record. A proposal can say implementable for
            years after its issue was closed as completed. Anyone who filters KEPs by status, as the process says the metadata
            is for, gets a wrong answer for those.
            {summary ? (
              <>
                {" "}
                In the SIGs loaded here, <strong className="text-fg">{fmt(summary.total)}</strong> records disagree across{" "}
                <strong className="text-fg">{fmt(summary.flagged_keps)}</strong> KEPs right now.
              </>
            ) : null}
          </p>
        </div>
      </Section>

      <Section id="how" eyebrow="How it works" title="Read everything live, keep the history, answer only from evidence.">
        <ol className="grid gap-6 md:grid-cols-3">
          <Step n="01" title="Ingest from public GitHub">
            The worker clones kubernetes/enhancements and kubernetes/community, reads OWNERS files and fetches tracking issues,
            timelines, pull requests and review threads. Nothing ships pre-populated.
          </Step>
          <Step n="02" title="One graph that remembers">
            Everything lands in a FalkorDB graph. Each state edge carries the interval it was valid for, so &ldquo;current&rdquo; and
            &ldquo;as of release X&rdquo; are the same graph with a different filter. Decisions are derived from the kep.yaml history
            and linked to the people who made them.
          </Step>
          <Step n="03" title="Answers with sources, or none">
            Five predicates compare the records pairwise and write each disagreement as a finding with both sides and a suggested
            fix. Questions run over read-only graph tools; a validator checks every claim cites a record returned in that request,
            or the answer is replaced by an abstention.
          </Step>
        </ol>
      </Section>

      <Section id="use" eyebrow="What you can do" title="Four ways in.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Door href={"/ask" as Route} title="Ask">
            Why a KEP is designed the way it is, who approved it, who knows an area, what changed since a release. Every answer
            shows the graph path it read.
          </Door>
          <Door href={"/explore" as Route} title="Explore">
            KEPs with their facts, status history, decisions and lineage; SIGs with their leadership; people with what they own
            and decide on.
          </Door>
          <Door href="/audit" title="Audit">
            Every record that disagrees, both sides linked to GitHub, who set each value, and a drafted fix. Nothing is ever posted.
          </Door>
          <Door href="/tools" title="Tools">
            The read-only graph tools behind every answer, callable directly, and the same catalog over MCP for other agents.
          </Door>
        </div>
      </Section>

      <Section id="honest" eyebrow="Honest by design" title="What it will not do.">
        <ul className="grid gap-4 text-md text-fg-secondary md:grid-cols-2">
          <li className="border-l-2 border-accent pl-4">It never answers from outside knowledge. No cited record, no claim.</li>
          <li className="border-l-2 border-accent pl-4">It never writes to GitHub. Fixes are drafted for a human to paste.</li>
          <li className="border-l-2 border-accent pl-4">
            It stores only public GitHub logins. E-mail addresses in the sources are never read into the graph.
          </li>
          <li className="border-l-2 border-accent pl-4">
            It shows its own uncertainty.
            {summary && summary.hand_checked != null ? (
              <>
                {" "}
                Today {fmt(summary.hand_checked)} of {fmt(summary.total)} findings are hand-checked, and the audit page says so.
              </>
            ) : (
              <> The audit page reports how many findings have been hand-checked.</>
            )}
          </li>
        </ul>
      </Section>

      <section className="border-t border-border px-6 py-20 text-center">
        <Mark className="mx-auto h-10 w-10" />
        <h2 className="display mt-6 text-xl font-semibold md:text-2xl">Start with a question.</h2>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Link
            href={"/ask" as Route}
            className="inline-flex h-11 items-center gap-2 rounded-md bg-accent px-5 text-md font-medium text-on-accent hover:bg-accent-hover"
          >
            Open KEP Brain
            <ArrowRight aria-hidden="true" size={16} strokeWidth={2} />
          </Link>
          <Link href="/about" className="quiet-link self-center text-md">
            How the data is handled
          </Link>
        </div>
      </section>
    </div>
  );
}

function Section({ id, eyebrow, title, children }: { id: string; eyebrow: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-16 border-t border-border px-6 py-20">
      <div className="mx-auto max-w-[1100px]">
        <p className="eyebrow">{eyebrow}</p>
        <h2 className="display mt-3 max-w-[26ch] text-xl font-semibold md:text-2xl">{title}</h2>
        <div className="mt-10">{children}</div>
      </div>
    </section>
  );
}

function Step({ n, title, children }: { n: string; title: string; children: React.ReactNode }) {
  return (
    <li className="rounded-md border border-border bg-surface p-5">
      <p className="font-mono text-xs text-accent">{n}</p>
      <h3 className="mt-2 text-md font-semibold">{title}</h3>
      <p className="mt-2 text-fg-secondary">{children}</p>
    </li>
  );
}

function Door({ href, title, children }: { href: Route; title: string; children: React.ReactNode }) {
  return (
    <Link href={href} className="group rounded-md border border-border bg-surface p-5 hover:border-border-strong">
      <h3 className="flex items-center justify-between text-md font-semibold">
        {title}
        <ArrowRight aria-hidden="true" size={16} strokeWidth={1.5} className="text-fg-muted group-hover:text-accent" />
      </h3>
      <p className="mt-2 text-fg-secondary">{children}</p>
    </Link>
  );
}

function Dot() {
  return (
    <span aria-hidden="true" className="text-border-strong">
      ·
    </span>
  );
}

/** The mark: three linked nodes, the same drawing as the favicon. */
function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 100 100" className={cx("shrink-0", className)} role="img" aria-label="KEP Brain">
      <rect width="100" height="100" rx="22" className="fill-surface stroke-border" strokeWidth="1" />
      <g className="stroke-accent" strokeOpacity="0.8" strokeWidth="5.5" strokeLinecap="round">
        <line x1="30" y1="30" x2="72" y2="50" />
        <line x1="72" y1="50" x2="30" y2="72" />
        <line x1="30" y1="30" x2="30" y2="72" />
      </g>
      <g className="fill-accent">
        <circle cx="30" cy="30" r="10" />
        <circle cx="72" cy="50" r="13" />
        <circle cx="30" cy="72" r="10" />
      </g>
    </svg>
  );
}
