import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Fully static. The site carries no secrets, needs no DataHub connection, and
  // has no server to misconfigure — it is a description of a local tool, not a
  // hosted service.
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
