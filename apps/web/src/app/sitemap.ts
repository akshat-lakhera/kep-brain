import type { MetadataRoute } from "next";
import { connection } from "next/server";
import { serverApi } from "@/lib/api/server";
import type { KepCard } from "@/lib/api/types";
import { routes } from "@/lib/routes";
import { siteBase } from "@/lib/site";

/** Public pages that exist regardless of the graph. /memory is per browser and /eval is internal, so neither is listed. */
const STATIC_PATHS = ["/", "/ask", "/explore", "/audit", "/tools", "/about"];

/** The API's largest page; a SIG with more KEPs than this is read per status as well. */
const PAGE = 300;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Read at request time: the graph changes independently of the web build, and so may the base URL.
  await connection();
  const base = siteBase();
  const entries: MetadataRoute.Sitemap = STATIC_PATHS.map((p) => ({ url: `${base}${p}` }));

  // When the API is down the static routes are still a valid sitemap.
  const sigs = await serverApi.sigs();
  if (!sigs.ok) return entries;
  const inScope = sigs.data.items.filter((s) => s.in_scope);
  for (const s of inScope) entries.push({ url: `${base}${routes.sig(s.key)}` });

  // KEP cards carry no modification date, so KEP entries list the URL only.
  const keps = await allKeps(inScope.map((s) => s.key));
  const seen = new Set<number>();
  for (const k of keps) {
    if (k.number === null || seen.has(k.number)) continue;
    seen.add(k.number);
    entries.push({ url: `${base}${routes.kep(k.number)}` });
  }
  // People have no list endpoint, so person pages are reached through the KEP and SIG pages instead.
  return entries;
}

/** Every KEP of the loaded SIGs: one page per SIG, split by status when a SIG fills a whole page. */
async function allKeps(sigKeys: string[]): Promise<KepCard[]> {
  const pages = await Promise.all(sigKeys.map((sig) => serverApi.keps({ sig, limit: PAGE })));
  const out: KepCard[] = [];
  for (let i = 0; i < pages.length; i++) {
    const page = pages[i];
    if (!page.ok) continue;
    if (page.data.items.length < PAGE) {
      out.push(...page.data.items);
      continue;
    }
    const byStatus = await Promise.all(
      Array.from(new Set(page.data.items.map((k) => k.status).filter((s): s is string => Boolean(s)))).map((status) =>
        serverApi.keps({ sig: sigKeys[i], status, limit: PAGE }),
      ),
    );
    out.push(...page.data.items);
    for (const r of byStatus) if (r.ok) out.push(...r.data.items);
  }
  return out;
}
