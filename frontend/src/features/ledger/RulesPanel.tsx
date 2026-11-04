import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  createRule,
  deleteRule,
  getMeta,
  getRules,
  previewRule,
  updateRule,
  type MatchField,
  type MatchType,
  type Rule,
} from "../../lib/api";

const MATCH_LABELS: Record<MatchType, string> = {
  contains: "contains",
  prefix: "starts with",
  exact: "is exactly",
};

type Scope = "all" | "user" | "seed";

/**
 * Rules are shown as editable data, not hidden heuristics.
 *
 * A categoriser people cannot inspect is one they cannot trust, so the built-in
 * suggestions are ordinary rows: switchable, re-pointable, deletable. The live
 * preview exists because a rule is a commitment — it should show what it will
 * touch before it touches it.
 */
export default function RulesPanel() {
  const queryClient = useQueryClient();
  const rulesQuery = useQuery({ queryKey: ["rules"], queryFn: getRules });
  const metaQuery = useQuery({ queryKey: ["meta"], queryFn: getMeta });

  const [pattern, setPattern] = useState("");
  const [debounced, setDebounced] = useState("");
  const [matchType, setMatchType] = useState<MatchType>("contains");
  const [field, setField] = useState<MatchField>("merchant");
  const [categoryId, setCategoryId] = useState("");
  const [scope, setScope] = useState<Scope>("all");
  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(pattern.trim()), 350);
    return () => window.clearTimeout(timer);
  }, [pattern]);

  const preview = useQuery({
    queryKey: ["rule-preview", debounced, matchType, field],
    queryFn: () => previewRule(debounced, matchType, field),
    enabled: debounced.length > 0,
  });

  const create = useMutation({
    mutationFn: () =>
      createRule({
        pattern: pattern.trim(),
        category_id: categoryId ? Number(categoryId) : null,
        match_type: matchType,
        field,
      }),
    onSuccess: (result) => {
      const count = `${result.applied} existing transaction${result.applied === 1 ? "" : "s"}`;
      setNotice(
        result.applied > 0
          ? `Rule saved — ${count} categorised now.`
          : "Rule saved. It will apply to future matches.",
      );
      setPattern("");
      setDebounced("");
      void queryClient.invalidateQueries();
    },
    onError: (error) =>
      setNotice(error instanceof Error ? error.message : "Could not save that rule."),
  });

  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      updateRule(id, { is_active: active }),
    onSuccess: () => void queryClient.invalidateQueries(),
    onError: (error) =>
      setNotice(error instanceof Error ? error.message : "Could not update that rule."),
  });

  const remove = useMutation({
    mutationFn: (id: number) => deleteRule(id),
    onSuccess: () => {
      setNotice("Rule deleted. Transactions it already categorised keep their category.");
      void queryClient.invalidateQueries();
    },
    onError: (error) =>
      setNotice(error instanceof Error ? error.message : "Could not delete that rule."),
  });

  const rules = rulesQuery.data ?? [];
  const categories = (metaQuery.data?.categories ?? []).filter(
    (category) => category.kind !== "income",
  );

  const visible = useMemo(() => {
    const needle = search.trim().toUpperCase();
    return rules.filter((rule) => {
      if (scope === "user" && rule.origin !== "user") return false;
      if (scope === "seed" && rule.origin !== "seed") return false;
      if (!needle) return true;
      return (
        rule.pattern.toUpperCase().includes(needle) ||
        (rule.category ?? "").toUpperCase().includes(needle)
      );
    });
  }, [rules, scope, search]);

  const userCount = rules.filter((rule) => rule.origin === "user").length;
  const seedCount = rules.length - userCount;
  const canSave = pattern.trim().length > 0 && categoryId !== "" && !create.isPending;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-base font-semibold tracking-tight">Rules</h2>
        <p className="mt-1 max-w-2xl text-[13px] text-mist">
          Rules run on import, most specific first. A manual choice always outranks a rule, and a
          rule outranks what SpendWise remembers about a merchant.
        </p>
      </div>

      {notice ? (
        <p className="rounded-md border border-accent/30 bg-accent/5 px-3 py-2 text-[12px] text-paper">
          {notice}
        </p>
      ) : null}

      <section className="panel p-4" aria-label="Create a rule">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1.6fr)_auto_auto_minmax(0,1fr)_auto] md:items-end">
          <div className="grid gap-1.5">
            <label className="text-[11px] tracking-wide text-faint uppercase" htmlFor="rule-pattern">
              Match text
            </label>
            <input
              id="rule-pattern"
              className="input"
              placeholder="e.g. BLUE TOKAI"
              value={pattern}
              onChange={(event) => setPattern(event.target.value)}
              autoComplete="off"
            />
          </div>

          <div className="grid gap-1.5">
            <label className="text-[11px] tracking-wide text-faint uppercase" htmlFor="rule-match">
              Match
            </label>
            <select
              id="rule-match"
              className="input"
              value={matchType}
              onChange={(event) => setMatchType(event.target.value as MatchType)}
            >
              {Object.entries(MATCH_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <div className="grid gap-1.5">
            <label className="text-[11px] tracking-wide text-faint uppercase" htmlFor="rule-field">
              In
            </label>
            <select
              id="rule-field"
              className="input"
              value={field}
              onChange={(event) => setField(event.target.value as MatchField)}
            >
              <option value="merchant">Merchant</option>
              <option value="raw">Narration</option>
            </select>
          </div>

          <div className="grid gap-1.5">
            <label className="text-[11px] tracking-wide text-faint uppercase" htmlFor="rule-category">
              Category
            </label>
            <select
              id="rule-category"
              className="input"
              value={categoryId}
              onChange={(event) => setCategoryId(event.target.value)}
            >
              <option value="">Choose…</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </div>

          <button
            type="button"
            className="btn btn-primary"
            disabled={!canSave}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Saving…" : "Add rule"}
          </button>
        </div>

        <div className="mt-3 min-h-5 text-[12px]">
          {debounced.length === 0 ? (
            <span className="text-faint">
              Type a merchant to preview how many transactions the rule would claim.
            </span>
          ) : preview.isLoading ? (
            <span className="text-faint">Checking matches…</span>
          ) : preview.isError ? (
            <span className="text-neg">
              {preview.error instanceof Error ? preview.error.message : "Preview failed."}
            </span>
          ) : preview.data ? (
            <span className="text-mist">
              Matches <span className="num text-paper">{preview.data.matched}</span> transaction
              {preview.data.matched === 1 ? "" : "s"} ·{" "}
              <span className="num text-paper">{preview.data.uncategorised}</span> currently
              uncategorised
              {preview.data.sample.length > 0 ? (
                <span className="text-faint">
                  {" "}
                  — {preview.data.sample.map((item) => item.merchant).join(", ")}
                </span>
              ) : null}
            </span>
          ) : null}
        </div>
      </section>

      <section className="panel overflow-hidden" aria-label="Rules list">
        <header className="panel-head gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <div className="segmented" role="group" aria-label="Filter rules">
              <button type="button" aria-pressed={scope === "all"} onClick={() => setScope("all")}>
                All {rules.length}
              </button>
              <button type="button" aria-pressed={scope === "user"} onClick={() => setScope("user")}>
                Mine {userCount}
              </button>
              <button type="button" aria-pressed={scope === "seed"} onClick={() => setScope("seed")}>
                Built-in {seedCount}
              </button>
            </div>
            <input
              className="input w-44"
              placeholder="Search rules"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search rules"
            />
          </div>
          <span className="panel-meta">
            {rulesQuery.isLoading ? "Loading…" : `${visible.length} shown`}
          </span>
        </header>

        {visible.length === 0 && !rulesQuery.isLoading ? (
          <p className="px-4 py-8 text-center text-sm text-faint">
            No rules match this filter. Add one above.
          </p>
        ) : (
          <ul className="divide-y divide-line/60">
            {visible.map((rule) => (
              <RuleRow
                key={rule.id}
                rule={rule}
                onToggle={(active) => toggle.mutate({ id: rule.id, active })}
                onDelete={() => remove.mutate(rule.id)}
                busy={toggle.isPending || remove.isPending}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function RuleRow({
  rule,
  onToggle,
  onDelete,
  busy,
}: {
  rule: Rule;
  onToggle: (active: boolean) => void;
  onDelete: () => void;
  busy: boolean;
}) {
  const isUser = rule.origin === "user";
  return (
    <li className="grid gap-2 px-4 py-2.5 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto_auto] md:items-center">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span
            className={`num truncate text-[13px] ${rule.is_active ? "text-paper" : "text-faint line-through"}`}
          >
            {rule.pattern}
          </span>
          <span className="pill pill-muted">{MATCH_LABELS[rule.match_type]}</span>
          {rule.field === "raw" ? <span className="pill pill-muted">narration</span> : null}
          {rule.is_transfer ? <span className="pill pill-muted">transfer</span> : null}
        </div>
        <p className="mt-0.5 text-[11px] text-faint">
          {isUser ? "Your rule" : "Built-in suggestion"} · priority {rule.priority}
        </p>
      </div>

      <div className="flex items-center gap-2">
        <span className="pill pill-neutral">{rule.category ?? "Uncategorised"}</span>
      </div>

      <span className="num text-[11px] text-faint md:text-right">
        {rule.applied_count > 0 ? `${rule.applied_count} applied` : "not applied"}
      </span>

      <div className="flex items-center justify-end gap-2">
        <label className="flex items-center gap-2 text-[11px] text-faint">
          <input
            type="checkbox"
            className="switch"
            checked={rule.is_active}
            disabled={busy}
            onChange={(event) => onToggle(event.target.checked)}
            aria-label={`${rule.is_active ? "Disable" : "Enable"} rule ${rule.pattern}`}
          />
          {rule.is_active ? "On" : "Off"}
        </label>
        {isUser ? (
          <button
            type="button"
            className="btn btn-ghost btn-icon text-faint hover:text-neg"
            onClick={onDelete}
            disabled={busy}
            title="Delete rule"
            aria-label={`Delete rule ${rule.pattern}`}
          >
            ×
          </button>
        ) : null}
      </div>
    </li>
  );
}
