"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

import { buttonClass, ErrorText, inputClass, useAction } from "@/components/story-ui";
import { type AuditEntry, getAuditLog } from "@/lib/api";
import { useApi } from "@/lib/useApi";

const timeFormat = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

// Text and a shape, so who did it never depends on colour alone.
const ACTORS: Record<AuditEntry["actor"], string> = {
  client: "● Client",
  team: "■ Team",
  ai: "◆ AI",
  github: "▲ GitHub",
  system: "○ System",
};

/** A8: everything that happened, newest first. Read-only; filter by project. */
export function AuditLog() {
  const router = useRouter();
  const project = useSearchParams().get("project") ?? "";
  const load = useCallback(
    (token: string, signal: AbortSignal) => getAuditLog(token, { project }, signal),
    [project],
  );
  const state = useApi(load);
  // Older pages, loaded with "Show older". Cleared when the filter changes.
  const [older, setOlder] = useState<{ project: string; events: AuditEntry[]; next: string | null }>({
    project,
    events: [],
    next: null,
  });
  const { busy, error, run } = useAction();

  if (state.kind === "loading") return <p role="status">Loading the audit log…</p>;
  if (state.kind === "error") {
    return <p role="status">{state.status === 403 ? "This page is only for our team." : "Could not load the audit log."}</p>;
  }

  const sameFilter = older.project === project;
  const events = [...state.data.events, ...(sameFilter ? older.events : [])];
  const next = sameFilter && older.events.length ? older.next : state.data.next;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-neutral-600 dark:text-neutral-300">
        Every AI output, change, approval and GitHub push. Entries are written by the app and can&apos;t
        be changed. They hold counts and IDs only, never what the client said.
      </p>

      <label className="flex flex-col gap-1 text-sm sm:max-w-xs">
        <span className="font-medium">Project</span>
        <select
          value={project}
          onChange={(e) => router.push(e.target.value ? `/admin/audit?project=${e.target.value}` : "/admin/audit")}
          className={inputClass}
        >
          <option value="">All projects</option>
          {state.data.projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} (#{p.id})
            </option>
          ))}
        </select>
      </label>

      {events.length === 0 ? (
        <p>Nothing recorded yet.</p>
      ) : (
        <ol className="flex flex-col divide-y divide-neutral-200 rounded-lg border border-neutral-300 dark:divide-neutral-800 dark:border-neutral-700">
          {events.map((event) => (
            <li key={event.id} className="grid gap-1 p-3 text-sm sm:grid-cols-[10rem_1fr]">
              <time dateTime={event.at} className="text-neutral-500 tabular-nums">
                {timeFormat.format(new Date(event.at))}
              </time>
              <div className="flex flex-col gap-0.5">
                <p>
                  <span className="font-medium">{event.label}</span>
                  {event.detail && <span className="text-neutral-600 dark:text-neutral-300"> · {event.detail}</span>}
                </p>
                <p className="text-xs text-neutral-500">
                  {ACTORS[event.actor] ?? event.actor} · {event.who} ·{" "}
                  {event.project_name ? (
                    <Link href={`/admin/projects/${event.project_id}`} className="underline">
                      {event.project_name}
                    </Link>
                  ) : (
                    `deleted project #${event.project_id}`
                  )}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}

      {next && (
        <button
          type="button"
          disabled={busy}
          className={`${buttonClass} self-start`}
          onClick={() =>
            run(async (token) => {
              const page = await getAuditLog(token, { project, before: next });
              setOlder((current) => ({
                project,
                events: [...(current.project === project ? current.events : []), ...page.events],
                next: page.next,
              }));
            })
          }
        >
          {busy ? "Loading…" : "Show older"}
        </button>
      )}
      <ErrorText error={error} />
    </div>
  );
}
