import { Auth } from "@auth/core";
import type { AuthConfig } from "@auth/core";
import { NextRequest } from "next/server";
import { authConfig } from "@/lib/auth-config";

// Next.js normalizes 127.0.0.1 → localhost in NextRequest.nextUrl, breaking
// Spotify's redirect_uri check (Spotify forbids localhost, requires 127.0.0.1).
// We bypass this by constructing a plain Request from AUTH_URL so the computed
// callbackUrl keeps the 127.0.0.1 origin that was registered with Spotify.
const AUTH_ORIGIN = process.env.AUTH_URL
  ? new URL(process.env.AUTH_URL).origin
  : "http://127.0.0.1:3000";

async function handler(req: NextRequest): Promise<Response> {
  const url = new URL(req.nextUrl.pathname + req.nextUrl.search, AUTH_ORIGIN);
  const plainReq = new Request(url.toString(), {
    method: req.method,
    headers: req.headers,
    body: req.method !== "GET" && req.method !== "HEAD" ? req.body : undefined,
    // @ts-expect-error duplex required for streaming request bodies in Node 18+
    duplex: "half",
  });
  return Auth(plainReq, authConfig as AuthConfig);
}

export const dynamic = "force-dynamic";
export const GET = handler;
export const POST = handler;
