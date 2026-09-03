import { NextRequest, NextResponse } from "next/server";

import { resolveApiOrigin } from "@/lib/api-origin";

export const dynamic = "force-dynamic";

function upstreamUrl(request: NextRequest, path: string[]): string {
  const suffix = path.map((segment) => encodeURIComponent(segment)).join("/");
  return `${resolveApiOrigin()}/${suffix}${request.nextUrl.search}`;
}

async function proxy(request: NextRequest, path: string[]): Promise<NextResponse> {
  if (path.length === 0 || path.some((segment) => segment === ".." || segment === ".")) {
    return NextResponse.json({ detail: "Invalid path" }, { status: 400 });
  }

  try {
    const response = await fetch(upstreamUrl(request, path), {
      cache: "no-store",
      headers: { accept: "application/json" },
    });
    const body = await response.arrayBuffer();
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json({ detail: "Upstream API unreachable" }, { status: 502 });
  }
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  return proxy(request, path);
}
