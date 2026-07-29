import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

// Both are SIL OFL. `next/font` downloads and self-hosts them at build time, so
// the deployed site makes no external requests — no Google Fonts call, nothing
// for a CSP to allow, nothing that leaks a visitor's IP to a third party.
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono-face",
  display: "swap",
});

const description =
  "Zence keeps Claude Code inside the correct client, domain, and environment " +
  "using DataHub's metadata graph. Open source, Apache-2.0.";

export const metadata: Metadata = {
  metadataBase: new URL("https://zence.site"),
  title: {
    default: "Zence — Keep every client in bounds",
    template: "%s — Zence",
  },
  description,
  openGraph: {
    title: "Zence — Keep every client in bounds",
    description,
    type: "website",
  },
  robots: { index: true, follow: true },
};

const REPO = "https://github.com/AmirmLotfy/zence";

const NAV = [
  { href: "/demo/", label: "Demo" },
  { href: "/verify/", label: "Verify" },
  { href: "/architecture/", label: "Architecture" },
  { href: "/security/", label: "Security" },
  { href: "/docs/", label: "Docs" },
  { href: "/open-source/", label: "Open source" },
];

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="min-h-screen flex flex-col">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded focus:bg-fg focus:px-3 focus:py-2 focus:text-bg"
        >
          Skip to content
        </a>

        <header className="border-b border-rule">
          <nav
            aria-label="Primary"
            className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-5 py-4"
          >
            <Link href="/" className="font-semibold tracking-tight">
              Zence
            </Link>
            <ul className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
              {NAV.map((item) => (
                <li key={item.href}>
                  <Link href={item.href} className="hover:text-fg">
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
            <a href={REPO} className="ml-auto text-sm text-muted hover:text-fg">
              GitHub ↗
            </a>
          </nav>
        </header>

        <main id="main" className="flex-1">
          {children}
        </main>

        <footer className="border-t border-rule text-sm text-muted">
          <div className="mx-auto grid max-w-5xl gap-8 px-5 py-10 sm:grid-cols-3">
            <div>
              <h2 className="font-medium text-fg">Source</h2>
              <ul className="mt-2 space-y-1">
                {[
                  ["Repository", `${REPO}`],
                  ["Policy engine", `${REPO}/tree/main/packages/zence-core/src/zence_core/policy`],
                  ["Decision artifacts", `${REPO}/tree/main/examples/artifacts/decisions`],
                  ["Demo catalog", `${REPO}/blob/main/demo/catalog/catalog.yaml`],
                ].map(([label, href]) => (
                  <li key={label}>
                    <a className="underline underline-offset-4 hover:text-fg" href={href}>
                      {label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <h2 className="font-medium text-fg">Reference</h2>
              <ul className="mt-2 space-y-1">
                {[
                  ["Threat model", `${REPO}/blob/main/docs/THREAT_MODEL.md`],
                  ["Policy engine reference", `${REPO}/blob/main/docs/POLICY_ENGINE.md`],
                  ["DataHub integration", `${REPO}/blob/main/docs/DATAHUB_INTEGRATION.md`],
                  ["Build status", `${REPO}/blob/main/TASKS.md`],
                ].map(([label, href]) => (
                  <li key={label}>
                    <a className="underline underline-offset-4 hover:text-fg" href={href}>
                      {label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <h2 className="font-medium text-fg">Zence</h2>
              <p className="mt-2">
                Apache-2.0. Runs on your machine; there is no hosted service.
              </p>
              <p className="mt-2">
                Built for{" "}
                <a
                  href="https://datahub.devpost.com/"
                  className="underline underline-offset-4 hover:text-fg"
                >
                  Build with DataHub: The Agent Hackathon
                </a>
              </p>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
