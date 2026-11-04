import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { assignMerchant, getMeta, getReview, runCategorisation } from "../../lib/api";

function shortDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
  });
}

/**
 * The review queue groups by merchant on purpose.
 *
 * Asking for a category per transaction trains people to stop reading. Asking
 * once per merchant is the same amount of thought for a fraction of the clicks,
 * and the answer is remembered for the next import.
 */
export default function ReviewQueue() {
  const queryClient = useQueryClient();
  const reviewQuery = useQuery({ queryKey: ["review"], queryFn: getReview });
  const metaQuery = useQuery({ queryKey: ["meta"], queryFn: getMeta });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);

  const assign = useMutation({
    mutationFn: ({ merchant, categoryId }: { merchant: string; categoryId: number }) =>
      assignMerchant(merchant, categoryId),
    onSuccess: (result) => {
      const count = `${result.updated} transaction${result.updated === 1 ? "" : "s"}`;
      setNotice(
        `${result.category} applied to ${count}${result.learned ? " — remembered for this merchant." : "."}`,
      );
      setDraft({});
      void queryClient.invalidateQueries();
    },
    onError: (error) =>
      setNotice(error instanceof Error ? error.message : "Could not apply that category."),
  });

  const rerun = useMutation({
    mutationFn: runCategorisation,
    onSuccess: (result) => {
      setNotice(
        result.applied === 0
          ? "No rule matched the remaining merchants."
          : `${result.applied} categorised by your rules and saved merchants.`,
      );
      void queryClient.invalidateQueries();
    },
  });

  const review = reviewQuery.data;
  const groups = review?.groups ?? [];
  const categories = metaQuery.data?.categories ?? [];
  const expenseCategories = categories.filter((category) => category.kind !== "income");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-tight">Needs a category</h2>
          <p className="mt-1 text-[13px] text-mist">
            Grouped by merchant, so one decision fixes every occurrence. Each answer is remembered
            for future imports.
          </p>
        </div>
        <button
          type="button"
          className="btn"
          onClick={() => rerun.mutate()}
          disabled={rerun.isPending}
        >
          {rerun.isPending ? "Running…" : "Re-run my rules"}
        </button>
      </div>

      {notice ? (
        <p className="rounded-md border border-accent/30 bg-accent/5 px-3 py-2 text-[12px] text-paper">
          {notice}
        </p>
      ) : null}

      {reviewQuery.isLoading ? <p className="text-sm text-faint">Loading review queue…</p> : null}

      {reviewQuery.isError ? (
        <p className="text-sm text-neg">
          {reviewQuery.error instanceof Error ? reviewQuery.error.message : "Could not load review."}
        </p>
      ) : null}

      {review && groups.length === 0 ? (
        <div className="empty">
          <div>
            <p className="text-sm text-paper">Every transaction has a category.</p>
            <p className="mt-1 text-xs text-faint">
              New imports land here when a merchant is unfamiliar.
            </p>
          </div>
        </div>
      ) : null}

      {groups.length > 0 ? (
        <section className="panel overflow-hidden">
          <header className="panel-head">
            <span className="panel-meta">
              {review?.total_unknown} transaction{review?.total_unknown === 1 ? "" : "s"} across{" "}
              {groups.length} merchant{groups.length === 1 ? "" : "s"}
            </span>
            <span className="panel-meta">Oldest first</span>
          </header>

          <ul className="divide-y divide-line/60">
            {groups.map((group) => {
              const value = draft[group.merchant] ?? "";
              return (
                <li
                  key={group.merchant}
                  className="grid gap-3 px-4 py-3 md:grid-cols-[minmax(0,1fr)_auto_auto] md:items-center"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-[13px] font-medium">{group.merchant}</span>
                      <span className="pill pill-neutral">
                        {group.count}×
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-[11px] text-faint" title={group.sample_raw}>
                      {group.sample_raw}
                    </p>
                    <p className="mt-0.5 text-[11px] text-faint">
                      {shortDate(group.first_on)} – {shortDate(group.last_on)} · {group.count}{" "}
                      transaction{group.count === 1 ? "" : "s"}
                    </p>
                  </div>

                  <span className="num text-[13px] text-mist md:text-right">{group.total}</span>

                  <div className="flex items-center gap-2">
                    <label className="sr-only" htmlFor={`category-${group.merchant}`}>
                      Category for {group.merchant}
                    </label>
                    <select
                      id={`category-${group.merchant}`}
                      className="input min-w-36"
                      value={value}
                      onChange={(event) =>
                        setDraft((current) => ({ ...current, [group.merchant]: event.target.value }))
                      }
                    >
                      <option value="">Choose a category…</option>
                      {expenseCategories.map((category) => (
                        <option key={category.id} value={category.id}>
                          {category.name}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={!value || assign.isPending}
                      onClick={() => value && assign.mutate({ merchant: group.merchant, categoryId: Number(value) })}
                    >
                      {assign.isPending ? "Applying…" : "Apply"}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
