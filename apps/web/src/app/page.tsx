import type { Metadata, Route } from "next";
import Link from "next/link";
import { connection } from "next/server";
import { Suspense } from "react";
import { ArrowRight, Download, GitBranch, ShieldCheck } from "lucide-react";
import { serverApi } from "@/lib/api/server";
import type { FindingsSummary, Meta } from "@/lib/api/types";
import { REPO_URL, SITE_DESCRIPTION, SITE_NAME, siteBase } from "@/lib/site";
import { cx } from "@/components/ui";
import { CountUp } from "@/components/CountUp";
import { JsonLd } from "@/components/JsonLd";
import { Mark } from "@/components/Mark";
import { Screenshot } from "@/components/Screenshot";
import askAnswer from "../../public/shots/ask-answer.png";
import askChain from "../../public/shots/ask-chain.png";
import kepDecisions from "../../public/shots/kep-decisions.png";
import auditDraft from "../../public/shots/audit-draft.png";

export const metadata: Metadata = { alternates: { canonical: "/" } };

/** The product's front door: what it is, the product itself in pictures, and how it earns its answers. */
export default function LandingPage() {
  // The hero needs no data; the live numbers stream in behind it so the route can be prerendered.
  return (
    <>
      <Suspense fallback={<Landing graph={null} summary={null} />}>
        <LiveLanding />
      </Suspense>
      <Suspense fallback={null}>
        <SiteJsonLd />
      </Suspense>
    </>
  );
}

/** What the site is, for crawlers. Read at request time so the URLs carry the deployment's base URL. */
async function SiteJsonLd() {
  await connection();
  const url = siteBase();
  return (
    <>
      <JsonLd data={{ "@context": "https://schema.org", "@type": "WebSite", name: SITE_NAME, url, description: SITE_DESCRIPTION }} />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "SoftwareApplication",
          name: SITE_NAME,
          url,
          description: SITE_DESCRIPTION,
          applicationCategory: "DeveloperApplication",
          operatingSystem: "Web",
          offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
          license: "https://opensource.org/licenses/MIT",
          sameAs: REPO_URL,
        }}
      />
    </>
  );
}

async function LiveLanding() {
  const [meta, findings] = await Promise.all([serverApi.meta(), serverApi.findings({})]);
  return <Landing graph={meta.ok ? meta.data.graph : null} summary={findings.ok ? findings.data.summary : null} />;
}

const IMAGE_SIZES = "(min-width: 1024px) 58vw, (min-width: 768px) 60vw, 100vw";

function Landing({ graph, summary }: { graph: Meta["graph"] | null; summary: FindingsSummary | null }) {
  const fmt = (n: number) => n.toLocaleString("en-US");

  return (
    <div className="-mx-4 -my-6 md:-mx-6">
      {/* 1. Hero */}
      <section className="overflow-x-clip px-4 pb-16 pt-12 md:px-6 md:pb-24 md:pt-20">
        <div className="mx-auto grid max-w-[1200px] items-center gap-10 lg:grid-cols-12 lg:gap-12">
          <div className="lg:col-span-5">
            <p>
              <span className="eyebrow-pill">The decision record of Kubernetes</span>
            </p>
            <h1 className="display mt-5 text-3xl text-fg md:text-4xl">Who decided, on what evidence, and what has gone stale.</h1>
            <p className="mt-5 max-w-[46ch] text-lead text-fg-secondary">
              KEP Brain reads the Kubernetes Enhancement Proposals, their tracking issues and pull requests into one graph, keeps
              the history of every state, and answers only from records it can cite.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link href={"/ask" as Route} className="btn btn-primary">
                Open KEP Brain
                <ArrowRight aria-hidden="true" size={16} strokeWidth={2} />
              </Link>
              <Link href="/audit" className="btn btn-secondary">
                See the audit
              </Link>
            </div>
            {graph ? (
              <dl className="mt-10 grid grid-cols-3 gap-4 border-t border-border pt-5">
                <Count value={graph.keps} label="KEPs" />
                <Count value={graph.people} label="people" />
                <Count value={graph.findings} label="records that disagree" href="/audit" />
              </dl>
            ) : null}
          </div>
          <div className="lg:col-span-7">
            <Screenshot
              src={askAnswer}
              alt="The Ask page in the dark theme: an answer explaining what a Kubernetes Enhancement Proposal is, with five numbered citations, beside its evidence chain of 11 nodes and 8 relations drawn as a diagram: the two KEP process documents and their sections, each node labelled, the five cited sections ringed, with a Diagram or List toggle above and a legend below."
              path="/ask"
              hero
              sizes={IMAGE_SIZES}
            />
          </div>
        </div>
      </section>

      {/* 2. Source strip */}
      <section className="border-y border-border bg-surface/60 px-4 py-4 md:px-6">
        <p className="mx-auto max-w-[1200px] text-center text-sm text-fg-muted">
          Reads live from <span className="ident text-fg-secondary">kubernetes/enhancements</span>,{" "}
          <span className="ident text-fg-secondary">kubernetes/community</span> and the{" "}
          <span className="ident text-fg-secondary">OWNERS</span> files; nothing ships pre-populated.
        </p>
      </section>

      {/* 3. Product sections */}
      <Feature
        id="ask"
        eyebrow="Ask"
        title="Every sentence cites a record in the graph."
        link={{ href: "/ask" as Route, label: "Ask a question" }}
        image={
          <Screenshot
            src={askChain}
            alt="An answer to what the status implementable means for a KEP, with one citation, beside its evidence chain of seven nodes and five relations drawn as a diagram: the Kubernetes Enhancement Proposals document linked to its sections, the cited KEP Workflow section ringed."
            path="/ask"
            sizes={IMAGE_SIZES}
          />
        }
      >
        Ask why a KEP is designed the way it is, who approved it, or what changed since a release. The answer shows the path it
        walked through the graph, and a validator drops any claim that no returned record supports.
      </Feature>

      <Feature
        id="kep"
        eyebrow="KEP page"
        title="Who decided each state, with the commit and pull request."
        link={{ href: "/explore" as Route, label: "Browse the KEPs" }}
        flip
        image={
          <Screenshot
            src={kepDecisions}
            alt="The Decisions tab of KEP-268: two decisions, each with the date, the decision text, the deciders by role, and the evidence links to the commit, status change, pull request and comment on GitHub."
            path="/explore/kep/268"
            sizes={IMAGE_SIZES}
          />
        }
      >
        Each KEP page lists its facts, status history, people and lineage. Decisions are derived from the kep.yaml history and
        the tracking issue, and each one names who decided, in which commit and pull request.
      </Feature>

      <Feature
        id="audit"
        eyebrow="Audit"
        title="Both records, their sources, and a drafted fix. Nothing is posted."
        link={{ href: "/audit", label: "See the audit" }}
        image={
          <Screenshot
            src={auditDraft}
            alt="The Audit page with a finding expanded and the Draft a fix dialog open: the issue title and Markdown body composed from the evidence, copy buttons, and a notice that nothing is posted."
            path="/audit"
            sizes={IMAGE_SIZES}
          />
        }
      >
        Five predicates compare kep.yaml, the tracking issue and the replacement declarations pairwise and write each
        disagreement as a finding. Expand one for both sides linked to GitHub, who set each value, and an issue text composed
        from the evidence for a human to paste.
      </Feature>

      {/* 4. How it works */}
      <Section id="how" eyebrow="How it works" title="Read everything live, keep the history, answer only from evidence.">
        <ol className="grid gap-4 md:grid-cols-3">
          <Step icon={Download} title="Ingest from public GitHub">
            Clones kubernetes/enhancements and kubernetes/community, reads the OWNERS files, and fetches tracking issues,
            timelines, pull requests and review threads.
          </Step>
          <Step icon={GitBranch} title="One graph that remembers">
            Every state edge carries the interval it was valid for, so &ldquo;current&rdquo; and &ldquo;as of a release&rdquo; are the
            same graph with a different filter.
          </Step>
          <Step icon={ShieldCheck} title="Answers with sources, or none">
            Questions run over read-only graph tools. A validator checks that every claim cites a record read in that request,
            or the answer becomes an abstention.
          </Step>
        </ol>
      </Section>

      {/* 5. One graph */}
      <Section id="graph" eyebrow="The graph" title="One FalkorDB graph does all of it.">
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Capability title="validity intervals">State edges carry valid-from and valid-to, so history is a filter, not a copy.</Capability>
          <Capability title="MERGE sync">Every ingest run is idempotent: re-running it changes nothing that has not changed.</Capability>
          <Capability title="read-only queries">Each tool runs a parameterised read-only query under a timeout; no tool writes.</Capability>
          <Capability title="PageRank">Ranks decisions by how the records around them connect, to weigh what matters in an area.</Capability>
          <Capability title="shortest paths">The evidence chain behind an answer is the shortest path between the records it cites.</Capability>
          <Capability title="full-text search">KEPs, people and SIGs are found through a full-text index, in the search box and the tools.</Capability>
        </ul>
      </Section>

      {/* 6. By design */}
      <Section id="honest" eyebrow="By design" title="Built to be checked.">
        <ul className="grid gap-x-10 gap-y-5 text-md text-fg-secondary md:grid-cols-2">
          <li className="border-l-2 border-accent pl-5">
            Every claim cites a record returned for that question; otherwise the answer is an abstention.
          </li>
          <li className="border-l-2 border-accent pl-5">GitHub is read-only: fixes are drafted for a human to paste.</li>
          <li className="border-l-2 border-accent pl-5">
            People are stored by public GitHub login only; e-mail addresses in the sources are never read into the graph.
          </li>
          <li className="border-l-2 border-accent pl-5">
            Uncertainty is shown:
            {summary && summary.hand_checked != null ? (
              <>
                {" "}
                today {fmt(summary.hand_checked)} of {fmt(summary.total)} findings are hand-checked, and the audit page says so.
              </>
            ) : (
              <> the audit page reports how many findings have been hand-checked.</>
            )}
          </li>
        </ul>
      </Section>

      {/* 7. Final call */}
      <section className="border-t border-border px-4 py-20 text-center md:px-6 md:py-24">
        <Mark className="mx-auto h-12 w-12" />
        <h2 className="display mt-6 text-2xl md:text-3xl">Start with a question.</h2>
        <p className="mx-auto mt-3 max-w-[40ch] text-lead text-fg-secondary">
          Or open a KEP and read who decided each state, and when the record last agreed with itself.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link href={"/ask" as Route} className="btn btn-primary">
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

/** One live count under the hero: the number ticks up once; the label is the quiet part. */
function Count({ value, label, href }: { value: number; label: string; href?: Route }) {
  const number = <CountUp value={value} className="tabular text-[28px] font-semibold leading-8 tracking-[-0.02em] text-fg" />;
  return (
    // A term comes before its definition in the markup; the number is moved above its label visually.
    <div className="flex flex-col">
      <dt className="mt-0.5 text-sm text-fg-muted">{label}</dt>
      <dd className="order-first">{href ? <Link href={href} className="quiet-link no-underline hover:underline">{number}</Link> : number}</dd>
    </div>
  );
}

/** A product section: text on one side, a framed screenshot on the other; `flip` swaps sides on desktop. */
function Feature({
  id,
  eyebrow,
  title,
  link,
  image,
  flip = false,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  link: { href: Route; label: string };
  image: React.ReactNode;
  flip?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-16 border-t border-border px-4 py-16 md:px-6 md:py-20">
      <div className="mx-auto grid max-w-[1200px] items-center gap-8 lg:grid-cols-12 lg:gap-12">
        <div className={cx("lg:col-span-5", flip && "lg:order-2")}>
          <p>
            <span className="eyebrow-pill">{eyebrow}</span>
          </p>
          <h2 className="display mt-4 text-2xl text-fg">{title}</h2>
          <p className="mt-4 max-w-[50ch] text-md text-fg-secondary">{children}</p>
          <Link href={link.href} className="quiet-link mt-5 inline-flex items-center gap-1.5 text-md font-medium">
            {link.label}
            <ArrowRight aria-hidden="true" size={16} strokeWidth={1.75} />
          </Link>
        </div>
        <div className={cx("lg:col-span-7", flip && "lg:order-1")}>{image}</div>
      </div>
    </section>
  );
}

function Section({ id, eyebrow, title, children }: { id: string; eyebrow: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-16 border-t border-border px-4 py-16 md:px-6 md:py-20">
      <div className="mx-auto max-w-[1200px]">
        <p>
          <span className="eyebrow-pill">{eyebrow}</span>
        </p>
        <h2 className="display mt-4 max-w-[30ch] text-2xl text-fg">{title}</h2>
        <div className="mt-10">{children}</div>
      </div>
    </section>
  );
}

function Step({ icon: Icon, title, children }: { icon: typeof Download; title: string; children: React.ReactNode }) {
  return (
    <li className="rounded-md border border-border bg-surface p-5 transition-colors hover:border-border-strong">
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-accent-subtle text-accent">
        <Icon aria-hidden="true" size={18} strokeWidth={1.75} />
      </span>
      <h3 className="mt-4 text-lg font-semibold tracking-[-0.01em]">{title}</h3>
      <p className="mt-2 text-fg-secondary">{children}</p>
    </li>
  );
}

function Capability({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <li className="rounded-md border border-border bg-surface p-5 transition-colors hover:border-border-strong">
      <h3 className="font-mono text-sm font-medium text-accent">{title}</h3>
      <p className="mt-2 text-sm text-fg-muted">{children}</p>
    </li>
  );
}
