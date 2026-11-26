"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { buttonClass, ErrorText, inputClass, useAction } from "@/components/story-ui";
import { type DataModel as DataModelData, getDataModel, type Project, writeDataModel } from "@/lib/api";
import { useApi } from "@/lib/useApi";

const dateFormat = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" });

/**
 * C6, AI5: the information the system will keep, as the AI understood it.
 *
 * Written automatically once the stories are ready. While reviewing, the
 * client can ask for a change; approving the stories confirms it.
 */
export function DataModel({ project }: { project: Project }) {
  const reviewing = project.status === "awaiting_client";
  const load = useCallback(
    (token: string, signal: AbortSignal) => getDataModel(token, project.id, signal),
    // Reload when the stage changes, e.g. right after the stories are written.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [project.id, project.status],
  );
  const state = useApi(load);
  const [written, setWritten] = useState<DataModelData | null>(null);
  const { busy, error, run } = useAction();
  const tried = useRef(false);

  const loaded = state.kind === "loaded" ? state.data.data_model : null;
  // A summary written on this page wins while reviewing; after approval the
  // reloaded one (now confirmed) does.
  const summary = reviewing ? (written ?? loaded) : (loaded ?? written);
  const missing = state.kind === "loaded" && !summary;

  // Write the summary once, as soon as the stories are ready for review.
  useEffect(() => {
    if (reviewing && missing && !tried.current) {
      tried.current = true;
      run(async (token) => setWritten((await writeDataModel(token, project.id)).data_model));
    }
  }, [reviewing, missing, project.id, run]);

  if (project.status === "interviewing" || state.kind === "loading") return null;

  return (
    <section aria-labelledby="data-model-heading" className="flex flex-col gap-3">
      <h2 id="data-model-heading" className="text-xl font-semibold">
        Your data
      </h2>
      {summary ? (
        <>
          <p className="text-sm text-neutral-600 dark:text-neutral-300">
            {summary.confirmed_at
              ? `What the system will keep. You confirmed this on ${dateFormat.format(new Date(summary.confirmed_at))}.`
              : "What the system will keep, as our AI understood it from your interview. Check it before you approve."}
          </p>
          <DataModelView summary={summary} />
        </>
      ) : busy ? (
        <p role="status" className="text-sm">
          Summarising the information your system will keep…
        </p>
      ) : (
        reviewing && (
          <button
            type="button"
            className={`${buttonClass} self-start`}
            onClick={() => run(async (token) => setWritten((await writeDataModel(token, project.id)).data_model))}
          >
            Summarise my data
          </button>
        )
      )}
      {reviewing && summary && <ChangeDataModel projectId={project.id} onChanged={setWritten} />}
      {!summary && <ErrorText error={error} />}
    </section>
  );
}

/** The entities as small tables, then how they connect. Shared with Team review. */
export function DataModelView({ summary }: { summary: DataModelData }) {
  return (
    <div className="flex flex-col gap-3">
      <ul className="grid gap-3 sm:grid-cols-2">
        {summary.entities.map((entity) => (
          <li key={entity.name} className="rounded-lg border border-neutral-300 p-4 text-sm dark:border-neutral-700">
            <h3 className="font-semibold">{entity.name}</h3>
            <p className="mb-2 text-neutral-600 dark:text-neutral-300">{entity.description}</p>
            <table className="w-full text-left">
              <caption className="sr-only">Fields of {entity.name}</caption>
              <thead>
                <tr className="text-xs text-neutral-500">
                  <th className="py-1 pr-2 font-medium">Field</th>
                  <th className="py-1 pr-2 font-medium">Type</th>
                  <th className="py-1 font-medium">Needed</th>
                </tr>
              </thead>
              <tbody>
                {entity.fields.map((field) => (
                  <tr key={field.name} className="border-t border-neutral-200 align-top dark:border-neutral-800">
                    <td className="py-1 pr-2">
                      {field.name}
                      {field.note && (
                        <span className="block text-xs text-neutral-500">{field.note}</span>
                      )}
                    </td>
                    <td className="py-1 pr-2">{summary.field_types[field.type] ?? field.type}</td>
                    <td className="py-1">{field.required ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </li>
        ))}
      </ul>
      {summary.relationship_sentences.length > 0 && (
        <div className="text-sm">
          <h3 className="font-semibold">How they connect</h3>
          <ul className="list-disc pl-5">
            {summary.relationship_sentences.map((sentence) => (
              <li key={sentence}>{sentence}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ChangeDataModel({
  projectId,
  onChanged,
}: {
  projectId: number;
  onChanged: (summary: DataModelData) => void;
}) {
  const [note, setNote] = useState("");
  const { busy, error, run } = useAction();

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        run(async (token) => {
          onChanged((await writeDataModel(token, projectId, note.trim())).data_model);
          setNote("");
        });
      }}
      className="flex flex-col gap-2 rounded-lg border border-neutral-300 p-4 text-sm dark:border-neutral-700"
    >
      <label className="flex flex-col gap-1">
        <span className="font-semibold">Something not right?</span>
        Tell us what to change, for example &quot;We also keep each customer&apos;s allergies&quot;.
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          maxLength={1000}
          className={inputClass}
        />
      </label>
      <button type="submit" disabled={busy || !note.trim()} className={`${buttonClass} self-start`}>
        {busy ? "Updating…" : "Update the summary"}
      </button>
      <ErrorText error={error} />
    </form>
  );
}
