import type { MetadataRoute } from "next";

// `output: export` has no request-time rendering, so this route has to declare
// itself static or the build refuses to collect it.
export const dynamic = "force-static";

/*
  Nothing here is private, so everything is crawlable. The one thing worth
  stating is the sitemap location, and the canonical host — the deployment also
  answers on a *.vercel.app URL, and without this a crawler can index the same
  seven pages twice under two names.
*/
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: "https://zence.site/sitemap.xml",
    host: "https://zence.site",
  };
}
