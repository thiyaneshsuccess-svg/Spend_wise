import { useState } from "react";
import Shell from "./components/Shell";
import LedgerPage from "./features/ledger/LedgerPage";
import PulsePage from "./features/pulse/PulsePage";

type View = "ledger" | "pulse" | "radar" | "horizon" | "lab";

export default function App() {
  const [view, setView] = useState<View>("ledger");

  return (
    <Shell active={view} onNavigate={(next) => setView(next as View)}>
      {view === "ledger" ? <LedgerPage /> : null}
      {view === "pulse" ? <PulsePage /> : null}
      {view === "radar" || view === "horizon" || view === "lab" ? (
        <div className="mx-auto max-w-6xl">
          <header>
            <h1 className="text-2xl font-semibold tracking-tight">
              {view === "radar" ? "Radar" : view === "horizon" ? "Horizon" : "Lab"}
            </h1>
            <p className="mt-1 text-sm text-mist">Coming in a later milestone.</p>
          </header>
          <section className="panel mt-6 p-8 text-center">
            <p className="text-sm text-mist">This engine is not implemented yet.</p>
          </section>
        </div>
      ) : null}
    </Shell>
  );
}
