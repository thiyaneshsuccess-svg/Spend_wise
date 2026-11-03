import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import {
  commitImport,
  previewImport,
  type Account,
  type ImportPreview,
} from "../../lib/api";

/**
 * Import with a dry run.
 *
 * The preview exists because a CSV import is the one action that can silently
 * corrupt a ledger. Showing new / duplicate / error counts *before* writing
 * turns an irreversible action into a reviewable one.
 */
export default function ImportDialog({
  accounts,
  onClose,
}: {
  accounts: Account[];
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [accountId, setAccountId] = useState(accounts[0]?.id ?? 0);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function handleFile(selected: File | null, targetAccount = accountId) {
    setFile(selected);
    setPreview(null);
    setDone(null);
    setError(null);
    if (!selected) return;

    setBusy(true);
    try {
      setPreview(await previewImport(selected, targetAccount));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not read that file.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCommit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await commitImport(file, accountId);
      await queryClient.invalidateQueries();
      setDone(
        `Imported ${result.imported} transactions, skipped ${result.skipped} duplicates.`,
      );
      setPreview(null);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Import failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="import-title"
      className="fixed inset-0 z-50 flex items-end justify-center bg-ink/80 p-4 backdrop-blur-sm sm:items-center"
    >
      <div className="card w-full max-w-2xl bg-panel p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="import-title" className="text-base font-semibold">
              Import a statement
            </h2>
            <p className="mt-1 text-xs text-mist">
              CSV with a date, description and amount — or separate debit/credit columns.
            </p>
          </div>
          <button type="button" className="btn px-2 py-1 text-xs" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs text-mist">
            Account
            <select
              className="input"
              value={accountId}
              onChange={(event) => {
                const next = Number(event.target.value);
                setAccountId(next);
                if (file) void handleFile(file, next);
              }}
            >
              {accounts.map((account) => (
                <option key={account.id} value={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-xs text-mist">
            CSV file
            <input
              ref={inputRef}
              type="file"
              accept=".csv,text/csv"
              className="input file:mr-3 file:rounded file:border-0 file:bg-panel file:px-2 file:py-1 file:text-xs file:text-paper"
              onChange={(event) => void handleFile(event.target.files?.[0] ?? null)}
            />
          </label>
        </div>

        {error ? (
          <p role="alert" className="mt-4 rounded-lg border border-neg/40 bg-neg/10 p-3 text-sm text-neg">
            {error}
          </p>
        ) : null}

        {done ? (
          <p className="mt-4 rounded-lg border border-pos/40 bg-pos/10 p-3 text-sm text-pos">{done}</p>
        ) : null}

        {busy && !preview ? <p className="mt-4 text-sm text-mist">Reading…</p> : null}

        {preview ? (
          <div className="mt-4">
            <div className="grid grid-cols-3 gap-2 text-center">
              <Stat label="Rows" value={preview.total_rows} />
              <Stat label="New" value={preview.new_rows} tone="pos" />
              <Stat label="Duplicates" value={preview.duplicates} tone="mist" />
            </div>

            {preview.errors.length > 0 ? (
              <ul className="mt-3 max-h-24 space-y-1 overflow-auto rounded-lg border border-neg/30 bg-neg/5 p-2 text-xs text-neg">
                {preview.errors.map((row) => (
                  <li key={`${row.line}-${row.message}`}>
                    Line {row.line}: {row.message}
                  </li>
                ))}
              </ul>
            ) : null}

            {preview.sample.length > 0 ? (
              <div className="mt-3 overflow-hidden rounded-lg border border-line">
                <table className="w-full text-xs">
                  <thead className="bg-panel-2 text-mist">
                    <tr>
                      <th className="px-2 py-1.5 text-left font-medium">Date</th>
                      <th className="px-2 py-1.5 text-left font-medium">Merchant</th>
                      <th className="px-2 py-1.5 text-right font-medium">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sample.map((row) => (
                      <tr key={row.line} className="border-t border-line/70">
                        <td className="num px-2 py-1.5 text-mist">{row.posted_on}</td>
                        <td className="px-2 py-1.5">{row.merchant}</td>
                        <td className="num px-2 py-1.5 text-right">{row.amount}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}

            <div className="mt-4 flex items-center justify-between gap-3">
              <p className="text-xs text-mist">
                Nothing is written until you confirm.
              </p>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || preview.new_rows === 0}
                onClick={() => void handleCommit()}
              >
                {busy ? "Importing…" : `Import ${preview.new_rows} transactions`}
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "pos" | "mist" }) {
  const color = tone === "pos" ? "text-pos" : tone === "mist" ? "text-mist" : "text-paper";
  return (
    <div className="rounded-lg border border-line bg-panel-2 py-2">
      <div className={`num text-lg font-semibold ${color}`}>{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-mist">{label}</div>
    </div>
  );
}
