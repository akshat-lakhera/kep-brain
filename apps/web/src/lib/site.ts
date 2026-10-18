/**
 * Facts about the site itself, shared by the metadata, the sitemap, robots.txt, the manifest and JSON-LD.
 * The base URL is read from the environment on each call, so it is the deployment's value, not the build's.
 */
export const SITE_NAME = "KEP Brain";

/** The landing page's one-line tagline. */
export const SITE_TAGLINE =
  "The decision record of Kubernetes in one graph: who decided, on what evidence, and where the records disagree.";

export const SITE_DESCRIPTION =
  "KEP Brain answers why a Kubernetes enhancement is designed the way it is, who decided and on what evidence, who owns and knows it, and whether its record is current, and lists the decision records that disagree.";

export const REPO_URL = "https://github.com/akshat-lakhera/kep-brain";

const FALLBACK_BASE = "http://localhost:3000";

/** Public origin of the site, without a trailing slash. */
export function siteBase(): string {
  const raw = process.env.PUBLIC_BASE_URL?.trim() || FALLBACK_BASE;
  try {
    return new URL(raw).toString().replace(/\/+$/, "");
  } catch {
    return FALLBACK_BASE;
  }
}

/** An absolute URL for an in-app path. */
export function absoluteUrl(path: string): string {
  return `${siteBase()}${path.startsWith("/") ? path : `/${path}`}`;
}
