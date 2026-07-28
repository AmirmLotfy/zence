import type { ReactNode } from "react";

export type Verdict = "allow" | "ask" | "deny";

/**
 * Verdict styling.
 *
 * Every verdict carries a glyph and a word alongside its colour. Colour is
 * never the only signal — that is what makes these legible to a colour-blind
 * reader, and in the greyscale screenshot someone inevitably puts in a slide.
 */
const VERDICT = {
  allow: {
    label: "Allowed",
    glyph: "✓",
    fg: "text-allow",
    bg: "bg-allow-soft",
    border: "border-allow",
  },
  ask: {
    label: "Approval required",
    glyph: "?",
    fg: "text-ask",
    bg: "bg-ask-soft",
    border: "border-ask",
  },
  deny: {
    label: "Denied",
    glyph: "✗",
    fg: "text-deny",
    bg: "bg-deny-soft",
    border: "border-deny",
  },
} as const;

export function VerdictBadge({
  verdict,
  ruleId,
}: {
  verdict: Verdict;
  ruleId?: string;
}) {
  const style = VERDICT[verdict];
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-medium ${style.fg} ${style.bg} ${style.border}`}
    >
      <span aria-hidden="true">{style.glyph}</span>
      {style.label}
      {ruleId ? (
        <span className="font-mono text-xs opacity-70">{ruleId}</span>
      ) : null}
    </span>
  );
}

export function Section({
  id,
  eyebrow,
  title,
  lede,
  children,
}: {
  id?: string;
  eyebrow?: string;
  title?: string;
  lede?: string;
  children?: ReactNode;
}) {
  return (
    <section
      id={id}
      className="border-t border-rule py-16 sm:py-20"
      aria-labelledby={id ? `${id}-title` : undefined}
    >
      <div className="mx-auto max-w-5xl px-5">
        {eyebrow ? (
          <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted">
            {eyebrow}
          </p>
        ) : null}
        {title ? (
          <h2
            id={id ? `${id}-title` : undefined}
            className="max-w-2xl text-balance text-2xl font-semibold tracking-tight sm:text-3xl"
          >
            {title}
          </h2>
        ) : null}
        {lede ? (
          <p className="mt-4 max-w-2xl text-pretty text-muted">{lede}</p>
        ) : null}
        {children ? <div className="mt-10">{children}</div> : null}
      </div>
    </section>
  );
}

export function Code({
  children,
  language,
  caption,
}: {
  children: string;
  language?: string;
  caption?: string;
}) {
  return (
    <figure>
      <div className="scroll-x rounded-lg border border-rule bg-surface">
        <pre className="p-4 font-mono text-[13px] leading-relaxed">
          <code data-language={language}>{children}</code>
        </pre>
      </div>
      {caption ? (
        <figcaption className="mt-2 text-sm text-muted">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
}

export function Card({
  title,
  children,
  accent,
}: {
  title: string;
  children: ReactNode;
  accent?: Verdict;
}) {
  const border = accent ? VERDICT[accent].border : "border-rule";
  return (
    <div className={`rounded-lg border ${border} bg-surface p-5`}>
      <h3 className="font-medium">{title}</h3>
      <div className="mt-2 text-sm text-muted">{children}</div>
    </div>
  );
}

/**
 * A labelled disclosure that a scenario is synthetic.
 *
 * Used anywhere the site shows a decision. The catalog is fictional and saying
 * so plainly costs nothing — a governance tool that blurs the line between a
 * demo and a production result has undermined its own argument.
 */
export function SyntheticNotice({ children }: { children?: ReactNode }) {
  return (
    <p className="rounded-md border border-rule bg-surface px-4 py-3 text-sm text-muted">
      {children ?? (
        <>
          <strong className="font-medium text-fg">
            Synthetic scenario.
          </strong>{" "}
          Northstar Commerce and BluePeak Health are fictional. These are real
          Zence decisions, recorded from actual runs against the demo catalog —
          not mock-ups — but no real company or person is represented.
        </>
      )}
    </p>
  );
}
