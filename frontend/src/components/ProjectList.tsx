"use client";

import Link from "next/link";

import { listProjects, PROJECT_STATUSES, PROJECT_TYPES } from "@/lib/api";
import { useApi } from "@/lib/useApi";

const dateFormat = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" });

export function ProjectList() {
  const state = useApi(listProjects);

  if (state.kind === "loading") {
    return <p role="status">Loading your projects…</p>;
  }
  if (state.kind === "error") {
    return <p role="status">Could not load your projects. Please try again.</p>;
  }
  if (state.data.length === 0) {
    return <p>You have no projects yet. Start one to record your first brief.</p>;
  }
  return (
    <ul className="flex flex-col gap-2">
      {state.data.map((project) => (
        <li key={project.id}>
          <Link
            href={`/projects/${project.id}`}
            className="flex items-center justify-between gap-4 rounded-lg border border-neutral-300 p-4 hover:border-neutral-500 dark:border-neutral-700"
          >
            <span className="flex flex-col">
              <span className="font-medium">{project.name}</span>
              <span className="text-sm text-neutral-600 dark:text-neutral-400">
                {PROJECT_TYPES[project.project_type]} · started{" "}
                {dateFormat.format(new Date(project.created_at))}
              </span>
            </span>
            <span className="rounded-full bg-neutral-100 px-3 py-1 text-xs dark:bg-neutral-800">
              {PROJECT_STATUSES[project.status]}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}