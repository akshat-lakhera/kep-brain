import type { MetadataRoute } from "next";
import { connection } from "next/server";
import { siteBase } from "@/lib/site";

export default async function robots(): Promise<MetadataRoute.Robots> {
  // Read at request time so the sitemap URL carries the deployment's base URL, not the build's.
  await connection();
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/api/", "/memory", "/eval", "/healthz"] }],
    sitemap: `${siteBase()}/sitemap.xml`,
  };
}
