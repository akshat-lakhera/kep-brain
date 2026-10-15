import type { ReleaseRef } from "./api/types";

/** Display name of a release reference ("v1.37"), whichever shape the API used. */
export function releaseName(r: ReleaseRef): string {
  if (typeof r === "string") return r;
  return r.name ?? r.key ?? "";
}

function version(name: string): [number, number] {
  const m = /(\d+)\.(\d+)/.exec(name);
  return m ? [Number(m[1]), Number(m[2])] : [Number.MAX_SAFE_INTEGER, 0];
}

/** Release names, oldest first, without blanks or duplicates. */
export function releaseNames(rs: ReleaseRef[] | null | undefined): string[] {
  const names = Array.from(new Set((rs ?? []).map(releaseName).filter(Boolean)));
  return names.sort((a, b) => {
    const [am, an] = version(a);
    const [bm, bn] = version(b);
    return am - bm || an - bn || a.localeCompare(b);
  });
}
