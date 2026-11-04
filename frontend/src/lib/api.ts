/**
 * Typed client for the SpendWise API.
 *
 * Kept deliberately small: one request helper, one function per endpoint. Every
 * type here mirrors a Pydantic schema in `backend/app/api/schemas.py`; when the
 * backend contract changes, TypeScript fails the build instead of the browser
 * failing at runtime with `undefined`.
 */

export type MatchType = "exact" | "prefix" | "contains";
export type MatchField = "merchant" | "raw";
export type RuleOrigin = "user" | "seed";

export interface Account {
  id: number;
  name: string;
  kind: string;
  institution: string | null;
}

export interface Category {
  id: number;
  name: string;
  kind: string;
}

export interface Meta {
  currency: string;
  timezone: string;
  demo_mode: boolean;
  accounts: Account[];
  categories: Category[];
  transaction_count: number;
  unknown_count: number;
  rule_count: number;
  first_transaction_on: string | null;
  last_transaction_on: string | null;
}

export interface Transaction {
  id: number;
  posted_on: string;
  merchant: string;
  merchant_raw: string;
  description: string | null;
  amount_minor: number;
  amount: string;
  currency: string;
  category: string | null;
  category_id: number | null;
  category_source: string;
  confidence: number | null;
  is_transfer: boolean;
  account: string;
  account_id: number;
}

export interface Summary {
  inflow_minor: number;
  inflow: string;
  outflow_minor: number;
  outflow: string;
  net_minor: number;
  net: string;
  count: number;
}

export interface TransactionPage {
  items: Transaction[];
  total: number;
  limit: number;
  offset: number;
  summary: Summary;
}

export interface ImportPreview {
  filename: string;
  total_rows: number;
  new_rows: number;
  duplicates: number;
  errors: { line: number; message: string }[];
  sample: {
    line: number;
    posted_on: string;
    merchant: string;
    amount_minor: number;
    amount: string;
    is_transfer: boolean;
  }[];
  currency: string;
}

export interface ImportResult {
  batch_id: number | null;
  total_rows: number;
  imported: number;
  skipped: number;
  errors: number;
  currency: string;
}

export interface SeedResult {
  created: number;
  skipped: boolean;
  months: number;
  start: string | null;
  end: string | null;
}

export interface Rule {
  id: number;
  pattern: string;
  match_type: MatchType;
  field: MatchField;
  category: string | null;
  category_id: number | null;
  priority: number;
  confidence: number;
  origin: string;
  is_transfer: boolean;
  is_active: boolean;
  applied_count: number;
}

export interface RuleMutation {
  rule: Rule;
  applied: number;
  remaining: number;
}

export interface RulePreview {
  matched: number;
  uncategorised: number;
  sample: { merchant: string; amount_minor: number; amount: string }[];
}

export interface RuleInput {
  pattern: string;
  category_id: number | null;
  match_type?: MatchType;
  field?: MatchField;
  priority?: number;
  is_transfer?: boolean;
}

export interface ReviewGroup {
  merchant: string;
  count: number;
  total_minor: number;
  total: string;
  first_on: string;
  last_on: string;
  sample_raw: string;
}

export interface Review {
  total_unknown: number;
  groups: ReviewGroup[];
}

export interface AssignResult {
  updated: number;
  propagated: number;
  learned: boolean;
  category: string | null;
}

export interface CategoriseRun {
  applied: number;
  remaining: number;
  by_source: Record<string, number>;
}

export interface CategorySlice {
  category_id: number | null;
  category: string;
  spent_minor: number;
  spent: string;
  count: number;
  share: number;
}

export interface Breakdown {
  month: string | null;
  total_spent_minor: number;
  total_spent: string;
  slices: CategorySlice[];
}

export interface PulseCategoryDelta {
  category_id: number | null;
  category: string;
  current_minor: number;
  current: string;
  baseline_minor: number;
  baseline: string;
  delta_minor: number;
  delta: string;
  current_count: number;
  baseline_count: number;
  change_pct: number | null;
}

export interface PulseMerchantDelta {
  merchant: string;
  category: string | null;
  category_id: number | null;
  current_minor: number;
  current: string;
  baseline_minor: number;
  baseline: string;
  delta_minor: number;
  delta: string;
}

export interface Pulse {
  month: string;
  baseline_months: string[];
  total_current_minor: number;
  total_current: string;
  total_baseline_minor: number;
  total_baseline: string;
  total_delta_minor: number;
  total_delta: string;
  categories: PulseCategoryDelta[];
  top_drivers: PulseMerchantDelta[];
  reconciles: boolean;
}

export interface TransactionQuery {
  month?: string;
  categoryId?: number;
  accountId?: number;
  q?: string;
  includeTransfers?: boolean;
  limit?: number;
  offset?: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // Keep the status-based message when the body is not JSON.
    }
    throw new Error(message);
  }
  // 204 has no body: returning undefined is correct for `void` calls.
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function getMeta(): Promise<Meta> {
  return request<Meta>("/api/meta");
}

export function getTransactions(query: TransactionQuery): Promise<TransactionPage> {
  const params = new URLSearchParams();
  if (query.month) params.set("month", query.month);
  if (query.categoryId) params.set("category_id", String(query.categoryId));
  if (query.accountId) params.set("account_id", String(query.accountId));
  if (query.q) params.set("q", query.q);
  if (query.includeTransfers) params.set("include_transfers", "true");
  params.set("limit", String(query.limit ?? 50));
  params.set("offset", String(query.offset ?? 0));
  return request<TransactionPage>(`/api/transactions?${params.toString()}`);
}

export function getBreakdown(month: string | undefined, includeTransfers = false): Promise<Breakdown> {
  const params = new URLSearchParams();
  if (month) params.set("month", month);
  if (includeTransfers) params.set("include_transfers", "true");
  return request<Breakdown>(`/api/breakdown?${params.toString()}`);
}

export function getPulse(month: string, lookback = 6, includeTransfers = false): Promise<Pulse> {
  const params = new URLSearchParams();
  params.set("month", month);
  params.set("lookback", String(lookback));
  if (includeTransfers) params.set("include_transfers", "true");
  return request<Pulse>(`/api/pulse?${params.toString()}`);
}

export function getRules(): Promise<Rule[]> {
  return request<Rule[]>("/api/rules");
}

export function createRule(input: RuleInput): Promise<RuleMutation> {
  return request<RuleMutation>("/api/rules", jsonInit("POST", input));
}

export function updateRule(
  id: number,
  changes: Partial<Omit<RuleInput, "pattern">> & { pattern?: string; is_active?: boolean },
): Promise<RuleMutation> {
  return request<RuleMutation>(`/api/rules/${id}`, jsonInit("PATCH", changes));
}

export function deleteRule(id: number): Promise<void> {
  return request<void>(`/api/rules/${id}`, { method: "DELETE" });
}

export function previewRule(
  pattern: string,
  matchType: MatchType,
  field: MatchField,
): Promise<RulePreview> {
  return request<RulePreview>(
    "/api/rules/preview",
    jsonInit("POST", { pattern, match_type: matchType, field }),
  );
}

export function runCategorisation(): Promise<CategoriseRun> {
  return request<CategoriseRun>("/api/categorise/run", { method: "POST" });
}

export function getReview(): Promise<Review> {
  return request<Review>("/api/review");
}

export function assignMerchant(merchant: string, categoryId: number): Promise<AssignResult> {
  return request<AssignResult>(
    "/api/review/assign",
    jsonInit("POST", { merchant, category_id: categoryId, remember: true }),
  );
}

export function setTransactionCategory(
  transactionId: number,
  categoryId: number | null,
  remember = true,
): Promise<AssignResult> {
  return request<AssignResult>(
    `/api/transactions/${transactionId}/category`,
    jsonInit("POST", { category_id: categoryId, remember }),
  );
}

export function seedDemo(months = 18): Promise<SeedResult> {
  return request<SeedResult>(`/api/dev/seed?months=${months}`, { method: "POST" });
}

function importForm(file: File, accountId: number): FormData {
  const form = new FormData();
  form.append("file", file);
  form.append("account_id", String(accountId));
  return form;
}

export function previewImport(file: File, accountId: number): Promise<ImportPreview> {
  return request<ImportPreview>("/api/imports/preview", {
    method: "POST",
    body: importForm(file, accountId),
  });
}

export function commitImport(file: File, accountId: number): Promise<ImportResult> {
  return request<ImportResult>("/api/imports/commit", {
    method: "POST",
    body: importForm(file, accountId),
  });
}
