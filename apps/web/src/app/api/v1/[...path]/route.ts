import http from "http";
import https from "https";
import { NextRequest, NextResponse } from "next/server";

const API_ORIGIN = process.env.API_URL ?? "http://127.0.0.1:8000";

const HOP_BY_HOP = new Set([
  "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
  "te", "trailers", "transfer-encoding", "upgrade",
  "host", "content-length",
]);

function proxyViaHttp(
  method: string,
  target: URL,
  reqHeaders: Headers,
  body?: Buffer,
): Promise<{ status: number; headers: Record<string, string>; body: Buffer }> {
  return new Promise((resolve, reject) => {
    const mod = target.protocol === "https:" ? https : http;
    const outHeaders: Record<string, string> = {};
    reqHeaders.forEach((v, k) => {
      if (!HOP_BY_HOP.has(k.toLowerCase())) outHeaders[k] = v;
    });
    if (body && body.byteLength > 0) {
      outHeaders["content-length"] = String(body.byteLength);
    }

    const req = mod.request(
      {
        hostname: target.hostname,
        port: target.port || (target.protocol === "https:" ? 443 : 80),
        path: target.pathname + target.search,
        method,
        headers: outHeaders,
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (chunk: Buffer) => chunks.push(chunk));
        res.on("end", () =>
          resolve({
            status: res.statusCode ?? 502,
            headers: res.headers as Record<string, string>,
            body: Buffer.concat(chunks),
          }),
        );
        res.on("error", reject);
      },
    );
    req.on("error", reject);
    if (body && body.byteLength > 0) req.write(body);
    req.end();
  });
}

async function proxy(req: NextRequest): Promise<NextResponse> {
  const suffix = req.nextUrl.pathname.replace(/^\/api\/v1/, "");
  const target = new URL(suffix + req.nextUrl.search, API_ORIGIN);

  let bodyBuf: Buffer | undefined;
  if (req.method !== "GET" && req.method !== "HEAD") {
    const ab = await req.arrayBuffer();
    if (ab.byteLength > 0) bodyBuf = Buffer.from(ab);
  }

  let result: Awaited<ReturnType<typeof proxyViaHttp>>;
  try {
    result = await proxyViaHttp(req.method, target, req.headers, bodyBuf);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ detail: `API unreachable: ${msg}` }, { status: 502 });
  }

  const contentType = result.headers["content-type"] ?? "application/json";
  return new NextResponse(new Uint8Array(result.body), {
    status: result.status,
    headers: { "content-type": contentType },
  });
}

export const dynamic = "force-dynamic";
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
