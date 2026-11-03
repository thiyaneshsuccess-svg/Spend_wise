import type { ReactNode } from "react";

/**
 * The application shell.
 *
 * The engine list is deliberately visible while only Ledger is live: it makes
 * the roadmap legible in the product itself instead of hiding in a README, and
 * it stops the UI from looking like a finished generic expense table.
 */

const ENGINES: { name: string; question: string; stage: string | null }[] = [
  { name: "Ledger", question: "What happened", stage: null },
  { name: "Pulse", question: "What changed", stage: "M3" },
  { name: "Radar", question: "Hidden costs", stage: "M4" },
  { name: "Horizon", question: "What comes next", stage: "M5" },
  { name: "Lab", question: "What if", stage: "M6" },
];

export default function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
      <aside className="border-b border-line bg-panel/60 px-4 py-4 lg:min-h-screen lg:border-r lg:border-b-0 lg:px-5 lg:py-6">
        <div className="flex items-center gap-2.5">
          <span aria-hidden className="size-2.5 rounded-sm bg-accent" />
          <span className="text-sm font-semibold tracking-[0.18em] text-paper">SPENDWISE</span>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-mist/80">
          Local-first finance intelligence
        </p>

        <nav aria-label="Engines" className="mt-6 flex gap-1 overflow-x-auto lg:flex-col">
          {ENGINES.map((engine) => {
            const active = engine.stage === null;
            return (
              <div
                key={engine.name}
                aria-current={active ? "page" : undefined}
                className={[
                  "flex shrink-0 items-baseline justify-between gap-3 rounded-lg px-3 py-2 text-sm lg:shrink",
                  active ? "bg-panel-2 text-paper" : "text-mist/70",
                ].join(" ")}
              >
                <span className="flex items-baseline gap-2">
                  <span className={active ? "font-medium" : ""}>{engine.name}</span>
                  <span className="hidden text-[11px] text-mist/60 xl:inline">
                    {engine.question}
                  </span>
                </span>
                {engine.stage ? (
                  <span className="chip border-line/70 text-[10px] uppercase tracking-wide">
                    {engine.stage}
                  </span>
                ) : (
                  <span aria-hidden className="size-1.5 rounded-full bg-accent" />
                )}
              </div>
            );
          })}
        </nav>

        <div className="mt-6 hidden rounded-lg border border-line/70 p-3 text-[11px] leading-relaxed text-mist/70 lg:block">
          Your transactions never leave this machine. Import a statement to begin.
        </div>
      </aside>

      <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-10">{children}</main>
    </div>
  );
}
