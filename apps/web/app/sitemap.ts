import type { MetadataRoute } from "next";

// `output: export` has no request-time rendering, so this route has to declare
// itself static or the build refuses to collect it.
export const dynamic = "force-static";

/*
  Every route, listed by hand. Seven pages do not need a generator, and a hand
  list fails loudly in the route check in CI if a page is added without one —
  which is the failure worth catching.
*/
const ROUTES = [
  "",
  "demo",
  "verify",
  "architecture",
  "security",
  "docs",
  "open-source",
] as const;

export default function sitemap(): MetadataRoute.Sitemap {
  return ROUTES.map((route) => ({
    url: `https://zence.site/${route ? `${route}/` : ""}`,
    changeFrequency: "weekly",
    priority: route === "" ? 1 : 0.8,
  }));
}
