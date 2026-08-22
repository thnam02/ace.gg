import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@valorant-scout/shared"],
};

export default nextConfig;
