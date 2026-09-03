import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Docker/Railway images need standalone. Vercel traces the app itself.
  ...(process.env.VERCEL ? {} : { output: "standalone" as const }),
};

export default nextConfig;
