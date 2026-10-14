import { connection } from "next/server";

/** Liveness of the web process itself (does not call the API). */
export async function GET(): Promise<Response> {
  await connection();
  return Response.json({ status: "ok" }, { headers: { "cache-control": "no-store" } });
}
