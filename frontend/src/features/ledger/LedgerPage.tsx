import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { getMeta, getTransactions, seedDemo } from "../../lib/api";
import ImportDialog from "./ImportDialog";

const PAGE_SIZE = 50;

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

function shortDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
  });
}

export default function LedgerPage() {
  const queryClient = useQueryClient();
  const metaQuery = useQuery({ queryKey: ["meta"], queryFn: getMeta });
  const meta = metaQuery.data;

  const [month, setMonth] = useState<string>("");
  const [categoryId, setCategoryId] = useState(0);
  const [accountId, setAccountId] = useState(0);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [includeTransfers, setIncludeTransfers] = useState(false);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (!meta?.last_transaction_on || month) return;
    setMonth(monthKey(meta.last_transaction_on));
  }, [meta, month]);

  const monthOptions = useMemo(() => {
    if (!meta?.first_transaction_on || !meta.last_transaction_on) return [];
    return monthsBetween(monthKey(meta.first_transaction_on), monthKey(meta.last_transaction_on));
  }, [meta]);

  useEffect(() => setLimit(PAGE_SIZE), [month, categoryId, accountId, debouncedQuery, includeTransfers]);

  const ledgerQuery = useQuery({
    queryKey: ["transactions", month, categoryId, accountId, debouncedQuery, includeTransfers, limit],
    queryFn: () =>
      getTransactions({
        month: month || undefined,
        categoryId: categoryId || undefined,
        accountId: accountId || undefined,
        q: debouncedQuery || undefined,
        includeTransfers,
        limit,
      }),
    enabled: Boolean(meta),
  });

  const seedMutation = useMutation({
    mutationFn: () => seedDemo(18),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      setMonth("");
    },
  });

  const page = ledgerQuery.data;
  const isEmpty = meta?.transaction_count === 0;

  return (
    <div className="mx-auto max-w-6xl">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Ledger</h1>
          <p className="mt-1 text-sm text-mist">
            Every transaction, normalised and deduplicated before it counts.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="chip">
            {meta?.currency ?? "—"} · {meta?.timezone ?? "local"}
          </span>
          <button type="button" className="btn" onClick={() => setImportOpen(true)}>
            Import CSV
          </button>
        </div>
      </header>

      {metaQuery.isError ? (
        <Banner tone="error">
          Could not reach the API. Start the backend, then reload.{" "}
          {metaQuery.error instanceof Error ? metaQuery.error.message : null}
        </Banner>
      ) : null}

      {isEmpty ? (
        <section className="card mt-8 p-8 text-center">
          <h2 className="text-lg font-medium">The ledger is empty</h2>
          <p className="mx-auto mt-2 max-w-md text-sm text-mist">
            Load 18 months of realistic demo data — salary, rent, subscriptions, a price hike, an
            anomalous purchase — or import your own statement.
          </p>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
            <button
              type="button"
              className="btn btn-primary"
              disabled={seedMutation.isPending}
              onClick={() => seedMutation.mutate()}
            >
              {seedMutation.isPending ? "Generating…" : "Generate demo ledger"}
            </button>
            <button type="button" className="btn" onClick={() => setImportOpen(true)}>
              Import CSV
            </button>
          </div>
          {seedMutation.isError ? (
            <p className="mt-4 text-sm text-neg">
              {seedMutation.error instanceof Error ? seedMutation.error.message : "Seeding failed."}
            </p>
          ) : null}
        </section>
      ) : null}

      {!isEmpty && meta ? (
        <>
          <section aria-label="Totals" className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric label="Money in" value={page?.summary.inflow ?? "—"} tone="pos" />
            <Metric label="Money out" value={page?.summary.outflow ?? "—"} />
            <Metric label="Net" value={page?.summary.net ?? "—"} tone="accent" />
            <Metric label="Transactions" value={page ? String(page.summary.count) : "—"} mono />
          </section>

          <section className="mt-4 flex flex-wrap items-center gap-2" aria-label="Filters">
            <label className="sr-only" htmlFor="month">
              Month
            </label>
            <select
              id="month"
              className="input"
              value={month}
              onChange={(event) => setMonth(event.target.value)}
            >
              <option value="">All time</option>
              {monthOptions.map((option) => (
                <option key={option} value={option}>
                  {monthLabel(option)}
                </option>
              ))}
            </select>

            <label className="sr-only" htmlFor="category">
              Category
            </label>
            <select
              id="category"
              className="input"
              value={categoryId}
              onChange={(event) => setCategoryId(Number(event.target.value))}
            >
              <option value={0}>All categories</option>
              {meta.categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>

            <label className="sr-only" htmlFor="account">
              Account
            </label>
            <select
              id="account"
              className="input"
              value={accountId}
              onChange={(event) => setAccountId(Number(event.target.value))}
            >
              <option value={0}>All accounts</option>
              {meta.accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>

            <input
              type="search"
              className="input min-w-48 flex-1"
              placeholder="Search merchant or narration"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Search transactions"
            />

            <label className="flex cursor-pointer items-center gap-2 text-xs text-mist">
              <input
                type="checkbox"
                className="size-3.5 accent-accent"
                checked={includeTransfers}
                onChange={(event) => setIncludeTransfers(event.target.checked)}
              />
              Show transfers
            </label>
          </section>

          <section className="card mt-4 overflow-hidden">
            {ledgerQuery.isLoading ? (
              <p className="p-8 text-center text-sm text-mist">Loading ledger…</p>
            ) : ledgerQuery.isError ? (
              <Banner tone="error">
                {ledgerQuery.error instanceof Error ? ledgerQuery.error.message : "Query failed."}
              </Banner>
            ) : page && page.items.length === 0 ? (
              <p className="p-10 text-center text-sm text-mist">
                No transactions match these filters.
              </p>
            ) : (
              <div className="max-h-[65vh] overflow-auto">
                <table className="w-full border-collapse text-sm">
                  <thead className="sticky top-0 z-10 bg-panel text-left text-[11px] uppercase tracking-wide text-mist">
                    <tr>
                      <th scope="col" className="px-4 py-2.5 font-medium">Date</th>
                      <th scope="col" className="px-4 py-2.5 font-medium">Merchant</th>
                      <th scope="col" className="px-4 py-2.5 font-medium">Category</th>
                      <th scope="col" className="px-4 py-2.5 font-medium">Account</th>
                      <th scope="col" className="px-4 py-2.5 text-right font-medium">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {page?.items.map((transaction) => (
                      <tr
                        key={transaction.id}
                        className="border-t border-line/70 transition-colors hover:bg-panel-2/60"
                      >
                        <td className="num whitespace-nowrap px-4 py-2.5 text-mist">
                          {shortDate(transaction.posted_on)}
                        </td>
                        <td className="max-w-72 px-4 py-2.5">
                          <div className="truncate font-medium">{transaction.merchant}</div>
                          <div
                            className="truncate text-[11px] text-mist/60"
                            title={transaction.merchant_raw}
                          >
                            {transaction.merchant_raw}
                          </div>
                        </td>
                        <td className="px-4 py-2.5">
                          {transaction.category ? (
                            <span className="chip">{transaction.category}</span>
                          ) : (
                            <span className="chip border-dashed border-amber-400/40 text-amber-300/90">
                              Uncategorised
                            </span>
                          )}
                          {transaction.is_transfer ? (
                            <span className="chip ml-1 border-line/70">transfer</span>
                          ) : null}
                        </td>
                        <td className="whitespace-nowrap px-4 py-2.5 text-mist">
                          {transaction.account}
                        </td>
                        <td
                          className={`num whitespace-nowrap px-4 py-2.5 text-right font-medium ${
                            transaction.amount_minor > 0 ? "text-pos" : "text-paper"
                          }`}
                        >
                          {transaction.amount}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {page && page.items.length > 0 ? (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 text-xs text-mist">
                <span>
                  Showing {page.items.length} of {page.total} transactions
                </span>
                {page.items.length < page.total ? (
                  <button
                    type="button"
                    className="btn px-2.5 py-1 text-xs"
                    onClick={() => setLimit((current) => current + PAGE_SIZE)}
                    disabled={ledgerQuery.isFetching}
                  >
                    {ledgerQuery.isFetching ? "Loading…" : `Load ${PAGE_SIZE} more`}
                  </button>
                ) : null}
              </div>
            ) : null}
          </section>
        </>
      ) : null}

      {importOpen && meta ? (
        <ImportDialog accounts={meta.accounts} onClose={() => setImportOpen(false)} />
      ) : null}
    </div>
  );
}

function Metric({
  label,
  value,
  tone,
  mono = false,
}: {
  label: string;
  value: string;
  tone?: "pos" | "accent";
  mono?: boolean;
}) {
  const color =
    tone === "pos" ? "text-pos" : tone === "accent" ? "text-accent" : "text-paper";
  return (
    <div className="card px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-mist">{label}</div>
      <div className={`mt-1 text-xl font-semibold ${mono ? "num" : "num"} ${color}`}>{value}</div>
    </div>
  );
}

function Banner({ tone, children }: { tone: "error"; children: React.ReactNode }) {
  const styles =
    tone === "error" ? "border-neg/40 bg-neg/10 text-neg" : "border-line bg-panel-2 text-mist";
  return <div className={`m-4 rounded-lg border p-3 text-sm ${styles}`}>{children}</div>;
}
