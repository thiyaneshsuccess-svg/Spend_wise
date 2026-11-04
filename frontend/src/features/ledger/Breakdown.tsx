import { useQuery } from "@tanstack/react-query";
import { getBreakdown } from "../../lib/api";

/**
 * Category spend for the selected month.
 *
 * The bars are scaled against the largest slice, not against 100%: with rent at
 * 46% of a month, a true-to-scale chart leaves every other category as a stub
 * that cannot be read. The percentage is printed, so nothing is exaggerated —
 * only the drawing is normalised.
 */
export default function Breakdown({
  month,
  monthLabel,
  includeTransfers,
  onSelectCategory,
}: {
  month: string | undefined;
  monthLabel: string;
  includeTransfers: boolean;
  onSelectCategory: (categoryId: number) => void;
}) {
  const query = useQuery({
    queryKey: ["breakdown", month, includeTransfers],
    queryFn: () => getBreakdown(month, includeTransfers),
  });

  const data = query.data;
  const slices = data?.slices ?? [];
  const max = Math.max(1, ...slices.map((slice) => slice.spent_minor));

  return (
    <section className="panel" aria-label="Spending by category">
      <header className="panel-head">
        <div>
          <h2 className="panel-title">Where the money went</h2>
          <p className="panel-meta mt-0.5">{monthLabel}</p>
        </div>
        {data ? <span className="num text-xs text-mist">{data.total_spent}</span> : null}
      </header>

      {query.isLoading ? (
        <p className="px-4 py-6 text-xs text-faint">Loading breakdown…</p>
      ) : query.isError ? (
        <p className="px-4 py-6 text-xs text-neg">
          {query.error instanceof Error ? query.error.message : "Could not load the breakdown."}
        </p>
      ) : slices.length === 0 ? (
        <p className="px-4 py-6 text-xs text-faint">No spending recorded in this period.</p>
      ) : (
        <ul className="divide-y divide-line/60">
          {slices.map((slice) => {
            const unknown = slice.category_id === null;
            const percent = Math.round(slice.share * 100);
            return (
              <li key={`${slice.category_id ?? "unknown"}-${slice.category}`}>
                <button
                  type="button"
                  disabled={unknown}
                  onClick={() => slice.category_id && onSelectCategory(slice.category_id)}
                  className="group w-full px-4 py-2.5 text-left enabled:cursor-pointer enabled:hover:bg-panel-2/50 disabled:cursor-default"
                  title={unknown ? "Categorise these in the Review tab" : `Filter the ledger to ${slice.category}`}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span
                      className={`truncate text-[13px] ${unknown ? "text-warn" : "text-paper group-enabled:group-hover:text-accent"}`}
                    >
                      {slice.category}
                    </span>
                    <span className="num shrink-0 text-[12px] text-mist">{slice.spent}</span>
                  </div>
                  <div className={`bar mt-1.5 ${unknown ? "bar-warn" : ""}`}>
                    <span style={{ width: `${Math.max(3, (slice.spent_minor / max) * 100)}%` }} />
                  </div>
                  <div className="mt-1 flex justify-between text-[10px] text-faint">
                    <span>
                      {slice.count} transaction{slice.count === 1 ? "" : "s"}
                    </span>
                    <span className="num">{percent}%</span>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
