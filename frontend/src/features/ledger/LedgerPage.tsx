import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  getMeta,
  getTransactions,
  seedDemo,
  setTransactionCategory,
  type Transaction,
} from "../../lib/api";
import Breakdown from "./Breakdown";
import ImportDialog from "./ImportDialog";
import ReviewQueue from "./ReviewQueue";
import RulesPanel from "./RulesPanel";

const PAGE_SIZE = 50;

const SOURCE_LABEL: Record<string, string> = {
  manual: "set by you",
  override: "set by you",
  rule: "by rule",
  memory: "remembered",
};

type Tab = "transactions" | "review" | "rules";

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

  const [tab, setTab] = useState<Tab>("transactions");
  const [month, setMonth] = useState<string>("");
  const [categoryId, setCategoryId] = useState(0);
  const [accountId, setAccountId] = useState(0);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [includeTransfers, setIncludeTransfers] = useState(false);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [importOpen, setImportOpen] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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

  useEffect(() => {
    setLimit(PAGE_SIZE);
  }, [month, categoryId, accountId, debouncedQuery, includeTransfers]);

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

  const categorise = useMutation({
    mutationFn: ({ id, nextCategoryId }: { id: number; nextCategoryId: number }) =>
      setTransactionCategory(id, nextCategoryId, true),
    onMutate: ({ id }) => {
      setBusyId(id);
      setNotice(null);
    },
    onSuccess: (result) => {
      setNotice(
        result.category
          ? `Set to ${result.category}. ${result.learned ? "Remembered for this merchant." : ""}`.trim()
          : "Category cleared.",
      );
      void queryClient.invalidateQueries();
    },
    onError: (error) =>
      setNotice(error instanceof Error ? error.message : "Could not update that transaction."),
    onSettled: () => setBusyId(null),
  });

  const page = ledgerQuery.data;
  const isEmpty = meta?.transaction_count === 0;
  const unknownCount = meta?.unknown_count ?? 0;

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
          <span className="pill pill-neutral">
            {meta?.currency ?? "—"} · {meta?.timezone ?? "local"}
          </span>
          <button type="button" className="btn" onClick={() => setImportOpen(true)}>
            Import CSV
          </button>
        </div>
      </header>

      {metaQuery.isError ? (
        <div className="mt-4 rounded-md border border-neg/40 bg-neg/10 p-3 text-sm text-neg">
          Could not reach the API. Start the backend, then reload.{" "}
          {metaQuery.error instanceof Error ? metaQuery.error.message : null}
        </div>
      ) : null}

      {isEmpty ? (
        <section className="panel mt-8 p-8 text-center">
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
          <section className="kpi-strip mt-6" aria-label="Totals for the selected period">
            <div className="kpi">
              <div className="kpi-label">Money in</div>
              <div className="kpi-value text-pos">{page?.summary.inflow ?? "—"}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Money out</div>
              <div className="kpi-value">{page?.summary.outflow ?? "—"}</div>
            </div>
            <div className="kpi">
              <div className="kpi-label">Net</div>
              <div
                className={`kpi-value ${(page?.summary.net_minor ?? 0) >= 0 ? "text-pos" : "text-neg"}`}
              >
                {page?.summary.net ?? "—"}
              </div>
            </div>
            <button
              type="button"
              className="kpi cursor-pointer text-left hover:bg-panel-2/50"
              onClick={() => setTab("review")}
              aria-label="Open the review queue"
            >
              <div className="kpi-label">Needs review</div>
              <div className={`kpi-value ${unknownCount > 0 ? "text-warn" : "text-mist"}`}>
                {unknownCount}
              </div>
            </button>
          </section>

          <div className="tabs mt-6" role="tablist" aria-label="Ledger views">
            <TabButton active={tab === "transactions"} onClick={() => setTab("transactions")}>
              Transactions
            </TabButton>
            <TabButton active={tab === "review"} onClick={() => setTab("review")}>
              Review
              {unknownCount > 0 ? <span className="pill pill-warn">{unknownCount}</span> : null}
            </TabButton>
            <TabButton active={tab === "rules"} onClick={() => setTab("rules")}>
              Rules
              <span className="pill pill-muted">{meta.rule_count}</span>
            </TabButton>
          </div>

          {tab === "transactions" ? (
            <div className="mt-4 grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)] lg:items-start">
              <div className="lg:sticky lg:top-6">
                <Breakdown
                  month={month || undefined}
                  monthLabel={month ? monthLabel(month) : "All time"}
                  includeTransfers={includeTransfers}
                  onSelectCategory={(id) => setCategoryId(id)}
                />
              </div>

              <div className="min-w-0">
                <section className="flex flex-wrap items-center gap-2" aria-label="Filters">
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
                    className="input min-w-44 flex-1"
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
                    Transfers
                  </label>
                </section>

                {notice ? (
                  <div className="mt-3 flex items-start justify-between gap-3 rounded-md border border-accent/30 bg-accent/5 px-3 py-2 text-[12px] text-paper">
                    <span>{notice}</span>
                    <button
                      type="button"
                      className="cursor-pointer text-faint hover:text-paper"
                      onClick={() => setNotice(null)}
                      aria-label="Dismiss message"
                    >
                      ×
                    </button>
                  </div>
                ) : null}

                <section className="panel mt-3 overflow-hidden">
                  {ledgerQuery.isLoading ? (
                    <p className="p-8 text-center text-sm text-mist">Loading ledger…</p>
                  ) : ledgerQuery.isError ? (
                    <p className="p-4 text-sm text-neg">
                      {ledgerQuery.error instanceof Error
                        ? ledgerQuery.error.message
                        : "Query failed."}
                    </p>
                  ) : page && page.items.length === 0 ? (
                    <div className="empty m-4">
                      <div>
                        <p className="text-sm text-paper">No transactions match these filters.</p>
                        <p className="mt-1 text-xs text-faint">
                          Clear the search or choose another month.
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="max-h-[62vh] overflow-auto">
                      <table className="ledger-table">
                        <thead className="sticky top-0 z-10 bg-panel">
                          <tr>
                            <th scope="col">Date</th>
                            <th scope="col">Merchant</th>
                            <th scope="col">Category</th>
                            <th scope="col" className="hidden sm:table-cell">
                              Account
                            </th>
                            <th scope="col" className="num">
                              Amount
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {page?.items.map((transaction) => (
                            <tr key={transaction.id}>
                              <td className="num whitespace-nowrap text-mist">
                                {shortDate(transaction.posted_on)}
                              </td>
                              <td className="max-w-64">
                                <div className="flex items-center gap-2">
                                  <span className="truncate font-medium">
                                    {transaction.merchant}
                                  </span>
                                  {transaction.is_transfer ? (
                                    <span className="pill pill-muted">transfer</span>
                                  ) : null}
                                </div>
                                <div
                                  className="truncate text-[11px] text-faint"
                                  title={transaction.merchant_raw}
                                >
                                  {transaction.merchant_raw}
                                </div>
                              </td>
                              <td>
                                <CategoryCell
                                  transaction={transaction}
                                  categories={meta.categories}
                                  busy={busyId === transaction.id}
                                  onChange={(nextCategoryId) =>
                                    categorise.mutate({ id: transaction.id, nextCategoryId })
                                  }
                                />
                              </td>
                              <td className="hidden whitespace-nowrap text-mist sm:table-cell">
                                {transaction.account}
                              </td>
                              <td
                                className={`num whitespace-nowrap text-right font-medium ${
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
              </div>
            </div>
          ) : null}

          {tab === "review" ? (
            <div className="mt-5">
              <ReviewQueue />
            </div>
          ) : null}

          {tab === "rules" ? (
            <div className="mt-5">
              <RulesPanel />
            </div>
          ) : null}
        </>
      ) : null}

      {importOpen && meta ? (
        <ImportDialog accounts={meta.accounts} onClose={() => setImportOpen(false)} />
      ) : null}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button type="button" role="tab" aria-selected={active} className="tab" onClick={onClick}>
      {children}
    </button>
  );
}

function CategoryCell({
  transaction,
  categories,
  busy,
  onChange,
}: {
  transaction: Transaction;
  categories: { id: number; name: string; kind: string }[];
  busy: boolean;
  onChange: (categoryId: number) => void;
}) {
  const source = SOURCE_LABEL[transaction.category_source];
  return (
    <div className="min-w-36">
      <label className="sr-only" htmlFor={`txn-category-${transaction.id}`}>
        Category for {transaction.merchant}
      </label>
      <select
        id={`txn-category-${transaction.id}`}
        className={`input h-7 max-w-40 text-[12px] ${transaction.category ? "" : "border-warn/40 text-warn"}`}
        value={transaction.category_id ?? ""}
        disabled={busy}
        onChange={(event) => onChange(Number(event.target.value))}
      >
        <option value="">Uncategorised</option>
        {categories.map((category) => (
          <option key={category.id} value={category.id}>
            {category.name}
          </option>
        ))}
      </select>
      <div className="mt-0.5 text-[10px] text-faint">{busy ? "saving…" : source ?? ""}</div>
    </div>
  );
}
