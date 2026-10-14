"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Citation } from "@/lib/api/types";

const CITE_PREFIX = "#cite-";

/** Turn "[1]" and "[^1]" markers into links the renderer recognises; leaves real Markdown links alone. */
function markCitations(md: string): string {
  return md.replace(/\[\^?(\d{1,3})\](?![(:[])/g, (_m, n: string) => `[[${n}]](${CITE_PREFIX}${n})`);
}

/**
 * Safe Markdown: no raw HTML (react-markdown escapes it by default and rehype-raw is not used), no images,
 * and links render only when they point at an evidence URL; citation markers become source links.
 */
export function AnswerMarkdown({ markdown, citations }: { markdown: string; citations: Citation[] }) {
  const byIndex = new Map(citations.map((c) => [c.index, c]));
  const evidenceUrls = new Set(citations.map((c) => c.url).filter((u): u is string => Boolean(u)));

  const components: Components = {
    a({ href, children }) {
      if (href?.startsWith(CITE_PREFIX)) {
        const n = Number(href.slice(CITE_PREFIX.length));
        const c = byIndex.get(n);
        if (!c) return <span className="font-mono text-sm text-fg-muted">[{n}]</span>;
        const name = `Source ${n}: ${c.label} ${c.title ?? c.key}`;
        const cls =
          "mx-0.5 inline-flex min-h-6 min-w-6 items-center justify-center rounded-sm bg-accent-subtle px-1 font-mono text-sm text-accent no-underline hover:text-accent-hover";
        return c.url ? (
          <a href={c.url} target="_blank" rel="noopener noreferrer" aria-label={name} title={name} className={cls}>
            {n}
          </a>
        ) : (
          <a href={`#source-${n}`} aria-label={name} title={name} className={cls}>
            {n}
          </a>
        );
      }
      if (href && evidenceUrls.has(href)) {
        return (
          <a href={href} target="_blank" rel="noopener noreferrer" className="prose-link">
            {children}
          </a>
        );
      }
      return <span>{children}</span>;
    },
  };

  return (
    <div className="answer">
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml disallowedElements={["img"]} unwrapDisallowed components={components}>
        {markCitations(markdown)}
      </ReactMarkdown>
    </div>
  );
}
