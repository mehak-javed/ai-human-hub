"use client";

import Link from "next/link";
import { useCallback, useState } from "react";

import { inputClass } from "@/components/story-ui";
import { listAdminProjects, PROJECT_TYPES, type ProjectStatus } from "@/lib/api";
import { useApi } from "@/lib/useApi";

// Labels from the team's point of view (the client sees friendlier ones).
const TEAM_STATUSES: Record<ProjectStatus, string> = {
  interviewing: "Interviewing",
  awaiting_client: "Awaiting client",
  awaiting_admin: "Awaiting our review",
  sent_to_github: "Sent to GitHub",
};

const dateFormat = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" });

/** Every client's projects, filtered by status and client (A3). */
export function AdminProjectList() {
  // What needs the team's attention comes first.
  const [status, setStatus] = useState<string>("awaiting_admin");
  const [client, setClient] = useState<string>("");

  const loadAll = useCallback(
    (token: string, signal: AbortSignal) => listAdminProjects(token, {}, signal),
    [],
  );
  const loadFiltered = useCallback(
    (token: string, signal: AbortSignal) => listAdminProjects(token, { status, client }, signal),
    [status, client],
  );
  const all = useApi(loadAll);
  const filtered = useApi(loadFiltered);

  if (all.kind === "error" || filtered.kind === "error") {
    const status = all.kind === "error" ? all.status : filtered.kind === "error" ? filtered.status : undefined;
    return (
      <p role="status">
        {status === 403 ? "This page is only for our team." : "Could not load the projects."}
      </p>
    );
  }
  if (all.kind === "loading" || filtered.kind === "loading") {
    return <p role="status">Loading projects…</p>;
  }

  const clients = [...new Map(all.data.map((p) => [p.client.id, p.client])).values()];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-4 text-sm">
        <label className="flex flex-col gap-1">
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)} className={inputClass}>
            <option value="">All</option>
            {Object.entries(TEAM_STATUSES).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          Client
          <select value={client} onChange={(e) => setClient(e.target.value)} className={inputClass}>
            <option value="">All clients</option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
                {c.email && c.email !== c.name ? ` (${c.email})` : ""}
              </option>
            ))}
          </select>
        </label>
      </div>

      {filtered.data.length === 0 ? (
        <p>No projects match.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {filtered.data.map((project) => (
            <li key={project.id}>
              <Link
                href={`/admin/projects/${project.id}`}
                className="flex items-center justify-between gap-4 rounded-lg border border-neutral-300 p-4 hover:border-neutral-500 dark:border-neutral-700"
              >
                <span className="flex flex-col">
                  <span className="font-medium">{project.name}</span>
                  <span className="text-sm text-neutral-600 dark:text-neutral-400">
                    {project.client.name} · {PROJECT_TYPES[project.project_type]} ·{" "}
                    {project.story_count} {project.story_count === 1 ? "story" : "stories"}
                    {project.approved_at &&
                      ` · approved ${dateFormat.format(new Date(project.approved_at))}`}
                  </span>
                </span>
                <span className="rounded-full bg-neutral-100 px-3 py-1 text-xs dark:bg-neutral-800">
                  {TEAM_STATUSES[project.status]}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
