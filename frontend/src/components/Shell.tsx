import type { ReactNode } from "react";

const ENGINES: { name: string; key: string; question: string; stage: string | null }[] = [
  { name: "Ledger", key: "ledger", question: "What happened", stage: null },
  { name: "Pulse", key: "pulse", question: "What changed", stage: null },
  { name: "Radar", key: "radar", question: "Hidden costs", stage: "M4" },
  { name: "Horizon", key: "horizon", question: "What comes next", stage: "M5" },
  { name: "Lab", key: "lab", question: "What if", stage: "M6" },
];

export default function Shell({
  children,
  active = "ledger",
  onNavigate,
}: {
  children: ReactNode;
  active?: string;
  onNavigate?: (key: string) => void;
}) {
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
            const isActive = active === engine.key;
            const clickable = engine.key === "ledger" || engine.key === "pulse";
            return (
              <button
                key={engine.name}
                type="button"
                onClick={() => clickable && onNavigate?.(engine.key)}
                aria-current={isActive ? "page" : undefined}
                className={[
                  "flex w-full shrink-0 items-baseline justify-between gap-3 rounded-lg px-3 py-2 text-left text-sm lg:shrink",
                  isActive ? "bg-panel-2 text-paper" : clickable ? "text-mist hover:bg-panel-2/40 hover:text-paper" : "text-mist/50",
                  !clickable ? "cursor-not-allowed" : "cursor-pointer",
                ].join(" ")}
                disabled={!clickable}
              >
                <span className="flex items-baseline gap-2">
                  <span className={isActive ? "font-medium" : ""}>{engine.name}</span>
                  <span className="hidden text-[11px] text-mist/60 xl:inline">
                    {engine.question}
                  </span>
                </span>
                {engine.stage ? (
                  <span className="pill pill-muted text-[10px] uppercase tracking-wide">
                    {engine.stage}
                  </span>
                ) : isActive ? (
                  <span aria-hidden className="size-1.5 rounded-full bg-accent" />
                ) : null}
              </button>
            );
          })}
        </nav>

        <div className="mt-6 hidden rounded-lg border border-line/70 p-3 text-[11px] leading-relaxed text-mist/70 lg:block">
          Your transactions never leave this machine.
        </div>
      </aside>

      <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-10 lg:py-10">{children}</main>
    </div>
  );
}
