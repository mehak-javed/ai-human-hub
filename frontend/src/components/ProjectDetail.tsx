"use client";

import { useCallback } from "react";

import { Transcripts } from "@/components/Transcripts";
import { getProject, PROJECT_STATUSES, PROJECT_TYPES } from "@/lib/api";
import { useApi } from "@/lib/useApi";

const dateTimeFormat = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
});

export function ProjectDetail({ id }: { id: string }) {
  const load = useCallback(
    (token: string, signal: AbortSignal) => getProject(token, id, signal),
    [id],
  );
  const state = useApi(load);

  if (state.kind === "loading") {
    return <p role="status">Loading project…</p>;
  }
  if (state.kind === "error") {
    return (
      <p role="status">
        {state.status === 404 ? "Project not found." : "Could not load this project."}
      </p>
    );
  }

  const project = state.data;
  return (
    <>
      <h1 className="text-3xl font-semibold">{project.name}</h1>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg border border-neutral-300 p-4 text-sm dark:border-neutral-700">
        <dt className="font-medium">Type</dt>
        <dd>{PROJECT_TYPES[project.project_type]}</dd>
        <dt className="font-medium">Status</dt>
        <dd>{PROJECT_STATUSES[project.status]}</dd>
        <dt className="font-medium">Consent given</dt>
        <dd>{dateTimeFormat.format(new Date(project.consent_given_at))}</dd>
      </dl>
      <Transcripts project={project} />
    </>
  );
}