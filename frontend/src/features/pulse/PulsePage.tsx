import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { getMeta, getPulse } from "../../lib/api";

function monthKey(iso: string): string {
  return iso.slice(0, 7);
}

function monthLabel(key: string): string {
  const [year, month] = key.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString("en-IN", {
    month: "long",
    year: "numeric",
  });
}

function monthsBetween(first: string, last: string): string[] {
  const [firstYear, firstMonth] = first.split("-").map(Number);
  const [lastYear, lastMonth] = last.split("-").map(Number);
  const months: string[] = [];
  let year = lastYear;
  let month = lastMonth;

  while (year > firstYear || (year === firstYear && month >= firstMonth)) {
    months.push(`${year}-${String(month).padStart(2, "0")}`);
    month -= 1;
    if (month === 0) {
      month = 12;
      year -= 1;
    }
  }
  return months;
}

export default function PulsePage() {
  const metaQuery = useQuery({ queryKey: ["meta"], queryFn: getMeta });
  const meta = metaQuery.data;
  const [month, setMonth] = useState<string>("");

  useEffect(() => {
    if (!meta?.last_transaction_on || month) return;
    setMonth(monthKey(meta.last_transaction_on));
  }, [meta, month]);

  const monthOptions = useMemo(() => {
    if (!meta?.first_transaction_on || !meta.last_transaction_on) return [];
    return monthsBetween(monthKey(meta.first_transaction_on), monthKey(meta.last_transaction_on));
  }, [meta]);

  const pulseQuery = useQuery({
    queryKey: ["pulse", month],
    queryFn: () => getPulse(month, 6),
    enabled: Boolean(month),
  });

  const pulse = pulseQuery.data;

  return (
    <div className="mx-auto max-w-6xl">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Pulse</h1>
          <p className="mt-1 text-sm text-mist">
            What changed this month vs the median of the last six months. Every delta reconciles.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="input"
            value={month}
            onChange={(event) => setMonth(event.target.value)}
            disabled={monthOptions.length === 0}
          >
            {monthOptions.map((option) => (
              <option key={option} value={option}>
                {monthLabel(option)}
              </option>
            ))}
          </select>
        </div>
      </header>

      {pulse ? (
        <>
          <section className="kpi-strip mt-6" aria-label="Period totals">
            <div className="kpi">
              <div className="kpi-label">This month</div>
              <div className="kpi-value">{pulse.total_current}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Baseline (median)</div>
              <div className="kpi-value">{pulse.total_baseline}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Change</div>
              <div
                className={`kpi-value ${
                  pulse.total_delta_minor > 0 ? "text-neg" : pulse.total_delta_minor < 0 ? "text-pos" : "text-mist"
                }`}
              >
                {pulse.total_delta_minor > 0 ? "+" : ""}
                {pulse.total_delta}
              </div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Reconciles</div>
              <div className={`kpi-value text-[18px] ${pulse.reconciles ? "text-pos" : "text-neg"}`}>
                {pulse.reconciles ? "Yes" : "No"}
              </div>
            </div>
          </section>

          <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] lg:items-start">
            <section className="panel overflow-hidden">
              <header className="panel-head">
                <div>
                  <h2 className="panel-title">By category</h2>
                  <p className="panel-meta mt-0.5">Biggest absolute changes first</p>
                </div>
                <span className="panel-meta">Median of {pulse.baseline_months.length} months</span>
              </header>
              <div className="table-wrap">
                <table className="ledger-table">
                  <thead>
                    <tr>
                      <th scope="col">Category</th>
                      <th scope="col" className="num">
                        This month
                      </th>
                      <th scope="col" className="num">
                        Baseline
                      </th>
                      <th scope="col" className="num">
                        Change
                      </th>
                      <th scope="col" className="num">
                        %
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {pulse.categories.map((cat) => (
                      <tr key={`${cat.category_id}-${cat.category}`}>
                        <td>
                          <span className="font-medium">{cat.category}</span>
                          <span className="ml-2 text-[11px] text-faint">
                            {cat.current_count} txn{cat.current_count === 1 ? "" : "s"}
                          </span>
                        </td>
                        <td className="num">{cat.current}</td>
                        <td className="num text-mist">{cat.baseline}</td>
                        <td
                          className={`num ${cat.delta_minor > 0 ? "text-neg" : cat.delta_minor < 0 ? "text-pos" : "text-mist"}`}
                        >
                          {cat.delta_minor > 0 ? "+" : ""}
                          {cat.delta}
                        </td>
                        <td className="num text-mist">
                          {cat.change_pct === null ? "—" : `${cat.change_pct > 0 ? "+" : ""}${cat.change_pct}%`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="panel overflow-hidden">
              <header className="panel-head">
                <div>
                  <h2 className="panel-title">Top drivers</h2>
                  <p className="panel-meta mt-0.5">Merchants moving the most</p>
                </div>
              </header>
              {pulse.top_drivers.length === 0 ? (
                <p className="px-4 py-6 text-xs text-faint">No large merchant-level swings this month.</p>
              ) : (
                <ul className="divide-y divide-line/60">
                  {pulse.top_drivers.map((driver, idx) => (
                    <li key={idx} className="px-4 py-2.5">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="truncate text-[13px] font-medium">{driver.merchant}</span>
                        <span
                          className={`num text-[12px] ${driver.delta_minor > 0 ? "text-neg" : "text-pos"}`}
                        >
                          {driver.delta_minor > 0 ? "+" : ""}
                          {driver.delta}
                        </span>
                      </div>
                      <div className="mt-0.5 flex justify-between text-[11px] text-faint">
                        <span>{driver.category ?? "Uncategorised"}</span>
                        <span>
                          {driver.baseline} → {driver.current}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </>
      ) : (
        <p className="mt-6 text-sm text-faint">
          {pulseQuery.isLoading ? "Loading pulse…" : "Select a month to see what changed."}
        </p>
      )}
    </div>
  );
}
