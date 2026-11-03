/**
 * Typed client for the SpendWise API.
 *
 * Kept deliberately small: one request helper, one function per endpoint. Every
 * type here mirrors a Pydantic schema in `backend/app/api/schemas.py`; when the
 * backend contract changes, TypeScript fails the build instead of the browser
 * failing at runtime with `undefined`.
 */

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
  return (await response.json()) as T;
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
