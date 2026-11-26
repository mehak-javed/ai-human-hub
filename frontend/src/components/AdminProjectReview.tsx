"use client";

import { type FormEvent, useCallback, useState } from "react";

import { DataModelView } from "@/components/DataModel";
import { GitHubDelivery } from "@/components/GitHubDelivery";
import {
  buttonClass,
  FormButtons,
  fromDraft,
  inputClass,
  PRIORITY_ORDER,
  ProgressBar,
  StoryFields,
  StoryForm,
  StoryText,
  toDraft,
  useAction,
} from "@/components/story-ui";
import {
  adminEditStory,
  adminMergeStories,
  adminRejectStory,
  adminSplitStory,
  type AdminProjectDetail,
  getAdminProject,
  type StoryChange,
  type StoryInput,
  type UserStory,
} from "@/lib/api";
import { useApi } from "@/lib/useApi";

const dateTimeFormat = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

const ACTION_LABELS: Record<StoryChange["action"], string> = {
  edit: "Edited",
  reject: "Rejected",
  merge: "Merged",
  split: "Split",
};

/** Combine several stories into a starting point for the merged one. */
function combine(stories: UserStory[]): StoryInput {
  const criteria = [...new Set(stories.flatMap((s) => s.acceptance_criteria))].slice(0, 8);
  const priority = PRIORITY_ORDER.find((p) => stories.some((s) => s.priority === p)) ?? "should";
  return {
    role: stories[0].role,
    goal: stories.map((s) => s.goal).join(" and "),
    reason: stories[0].reason,
    acceptance_criteria: criteria,
    priority,
  };
}

/** Our team's review of one client-approved project (A4). */
export function AdminProjectReview({ id }: { id: string }) {
  // Bumped after every change, so the page reloads the stories and change log.
  const [version, setVersion] = useState(0);
  const load = useCallback(
    (token: string, signal: AbortSignal) => getAdminProject(token, id, signal),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- version triggers a reload
    [id, version],
  );
  const state = useApi(load);
  const [selected, setSelected] = useState<number[]>([]);
  const [merging, setMerging] = useState(false);

  if (state.kind === "loading") {
    return <p role="status">Loading project…</p>;
  }
  if (state.kind === "error") {
    return (
      <p role="status">
        {state.status === 403
          ? "This page is only for our team."
          : state.status === 404
            ? "Project not found."
            : "Could not load this project."}
      </p>
    );
  }

  const project = state.data;
  const editable = project.status === "awaiting_admin";
  const changed = () => {
    setSelected([]);
    setMerging(false);
    setVersion((v) => v + 1);
  };
  const toggle = (storyId: number) =>
    setSelected((current) =>
      current.includes(storyId) ? current.filter((x) => x !== storyId) : [...current, storyId],
    );
  const selectedStories = project.stories.filter((s) => selected.includes(s.id));

  return (
    <div className="flex flex-col gap-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-3xl font-semibold">{project.name}</h1>
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          {project.client.name}
          {project.client.email && project.client.email !== project.client.name && ` · ${project.client.email}`}
          {project.approved_at && ` · approved by the client ${dateTimeFormat.format(new Date(project.approved_at))}`}
        </p>
        {!editable && (
          <p className="mt-2 rounded-md bg-neutral-100 p-3 text-sm dark:bg-neutral-900">
            {project.status === "sent_to_github"
              ? "These stories have been sent to GitHub, so they can no longer be changed."
              : "The client hasn't approved these stories yet, so they can't be reviewed."}
          </p>
        )}
      </header>

      <ClientWords project={project} />

      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xl font-semibold">Stories ({project.stories.length})</h2>
          {editable && (
            <button
              type="button"
              disabled={selected.length < 2}
              onClick={() => setMerging(true)}
              className={buttonClass}
            >
              Merge {selected.length >= 2 ? `${selected.length} selected` : "selected"}
            </button>
          )}
        </div>
        {editable && !merging && (
          <p className="text-sm text-neutral-600 dark:text-neutral-300">
            Tick two or more overlapping stories to merge them. Every change is recorded with your
            name.
          </p>
        )}

        {merging && (
          <MergeEditor
            projectId={project.id}
            stories={selectedStories}
            onCancel={() => setMerging(false)}
            onDone={changed}
          />
        )}

        <ol className="flex flex-col gap-3">
          {project.stories.map((story) => (
            <AdminStoryCard
              key={story.id}
              projectId={project.id}
              story={story}
              editable={editable}
              selected={selected.includes(story.id)}
              onToggle={() => toggle(story.id)}
              onChanged={changed}
            />
          ))}
        </ol>
      </section>

      {project.data_model && (
        <section aria-labelledby="team-data-heading" className="flex flex-col gap-3">
          <h2 id="team-data-heading" className="text-xl font-semibold">
            Data model
          </h2>
          <p className="text-sm text-neutral-600 dark:text-neutral-300">
            Written by AI from the masked interview
            {project.data_model.confirmed_at ? " and confirmed by the client" : ""}. It goes into
            requirements.md.
          </p>
          <DataModelView summary={project.data_model} />
        </section>
      )}

      {project.progress && <ProgressBar progress={project.progress} />}

      <GitHubDelivery project={project} onChanged={changed} />

      <ChangeLog changes={project.changes} />
    </div>
  );
}

function ClientWords({ project }: { project: AdminProjectDetail }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-xl font-semibold">What the client told us</h2>
      <p className="text-xs text-neutral-500">
        Personal details are hidden here too, the same way as for the AI.
      </p>
      {project.masked_transcripts.map((text, index) => (
        <p key={index} className="whitespace-pre-wrap rounded-md bg-neutral-100 p-3 text-sm dark:bg-neutral-900">
          {text}
        </p>
      ))}
      {project.answers.length > 0 && (
        <dl className="flex flex-col gap-2 text-sm">
          {project.answers.map((qa, index) => (
            <div key={index}>
              <dt className="font-medium">{qa.question}</dt>
              <dd className="whitespace-pre-wrap text-neutral-700 dark:text-neutral-300">{qa.answer}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

type Mode = "view" | "edit" | "split" | "reject";

function AdminStoryCard({
  projectId,
  story,
  editable,
  selected,
  onToggle,
  onChanged,
}: {
  projectId: number;
  story: UserStory;
  editable: boolean;
  selected: boolean;
  onToggle: () => void;
  onChanged: () => void;
}) {
  const [mode, setMode] = useState<Mode>("view");
  const { busy, error, run } = useAction();
  const cancel = () => setMode("view");

  return (
    <li className="flex gap-3 rounded-lg border border-neutral-300 p-4 dark:border-neutral-700">
      {editable && mode === "view" && (
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          aria-label={`Select "${story.goal}" to merge`}
          className="mt-1"
        />
      )}
      <div className="flex flex-1 flex-col gap-2">
        <p className="text-xs uppercase tracking-wide text-neutral-500">
          {story.priority} · {story.origin === "ai" ? (story.client_edited ? "AI, changed by client" : "AI") : story.origin}
        </p>

        {mode === "edit" ? (
          <StoryForm
            initial={story}
            submitLabel="Save changes"
            onCancel={cancel}
            onSubmit={(input) =>
              run(async (token) => {
                await adminEditStory(token, projectId, story.id, input);
                // Close the form, so a second press can't save the same edit twice.
                setMode("view");
                onChanged();
              })
            }
            busy={busy}
            error={error}
          />
        ) : mode === "split" ? (
          <SplitEditor projectId={projectId} story={story} onCancel={cancel} onDone={onChanged} />
        ) : (
          <StoryText story={story} />
        )}

        {mode === "reject" && (
          <RejectForm projectId={projectId} story={story} onCancel={cancel} onDone={onChanged} />
        )}

        {editable && mode === "view" && (
          <div className="flex gap-3 text-sm">
            <button type="button" onClick={() => setMode("edit")} className="underline">
              Edit
            </button>
            <button type="button" onClick={() => setMode("split")} className="underline">
              Split
            </button>
            <button type="button" onClick={() => setMode("reject")} className="text-red-600 underline">
              Reject
            </button>
          </div>
        )}
      </div>
    </li>
  );
}

function RejectForm({
  projectId,
  story,
  onCancel,
  onDone,
}: {
  projectId: number;
  story: UserStory;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const { busy, error, run } = useAction();

  function submit(event: FormEvent) {
    event.preventDefault();
    run(async (token) => {
      await adminRejectStory(token, projectId, story.id, reason.trim());
      onDone();
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2 text-sm">
      <label className="flex flex-col gap-1">
        Why should this story not be built?
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          required
          rows={2}
          maxLength={500}
          className={inputClass}
        />
      </label>
      <FormButtons submitLabel="Reject story" onCancel={onCancel} busy={busy} error={error} />
    </form>
  );
}

function SplitEditor({
  projectId,
  story,
  onCancel,
  onDone,
}: {
  projectId: number;
  story: UserStory;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [parts, setParts] = useState(() => [toDraft(story), toDraft(story)]);
  const { busy, error, run } = useAction();

  function submit(event: FormEvent) {
    event.preventDefault();
    run(async (token) => {
      await adminSplitStory(token, projectId, story.id, parts.map(fromDraft));
      onDone();
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4 text-sm">
      <p>Split this story into smaller ones. They take its place in the list.</p>
      {parts.map((part, index) => (
        <fieldset key={index} className="flex flex-col gap-3 rounded-md border border-neutral-300 p-3 dark:border-neutral-700">
          <legend className="px-1 font-medium">Part {index + 1}</legend>
          <StoryFields
            value={part}
            onChange={(draft) => setParts((current) => current.map((p, i) => (i === index ? draft : p)))}
          />
          {parts.length > 2 && (
            <button
              type="button"
              onClick={() => setParts((current) => current.filter((_, i) => i !== index))}
              className="self-start text-red-600 underline"
            >
              Remove this part
            </button>
          )}
        </fieldset>
      ))}
      {parts.length < 10 && (
        <button
          type="button"
          onClick={() => setParts((current) => [...current, toDraft(story)])}
          className={`${buttonClass} self-start`}
        >
          Add another part
        </button>
      )}
      <FormButtons submitLabel={`Split into ${parts.length} stories`} onCancel={onCancel} busy={busy} error={error} />
    </form>
  );
}

function MergeEditor({
  projectId,
  stories,
  onCancel,
  onDone,
}: {
  projectId: number;
  stories: UserStory[];
  onCancel: () => void;
  onDone: () => void;
}) {
  const [draft, setDraft] = useState(() => toDraft(combine(stories)));
  const { busy, error, run } = useAction();

  function submit(event: FormEvent) {
    event.preventDefault();
    run(async (token) => {
      await adminMergeStories(
        token,
        projectId,
        stories.map((s) => s.id),
        fromDraft(draft),
      );
      onDone();
    });
  }

  return (
    <form
      onSubmit={submit}
      className="flex flex-col gap-3 rounded-lg border border-dashed border-neutral-400 p-4 text-sm"
    >
      <h3 className="font-semibold">Merge {stories.length} stories into one</h3>
      <ul className="list-disc pl-5 text-neutral-600 dark:text-neutral-300">
        {stories.map((s) => (
          <li key={s.id}>{s.goal}</li>
        ))}
      </ul>
      <StoryFields value={draft} onChange={setDraft} />
      <FormButtons submitLabel="Merge stories" onCancel={onCancel} busy={busy} error={error} />
    </form>
  );
}

const FIELD_LABELS: Record<string, string> = {
  role: "who",
  goal: "what they want",
  reason: "why",
  acceptance_criteria: "checks",
  priority: "priority",
};

/** One line saying what changed: which fields for an edit, which stories otherwise. */
export function describeChange(change: StoryChange): string {
  const [before] = change.before;
  const [after] = change.after;
  if (change.action === "edit" && before && after) {
    const changed = Object.keys(FIELD_LABELS).filter(
      (field) =>
        JSON.stringify(before[field as keyof StoryInput]) !== JSON.stringify(after[field as keyof StoryInput]),
    );
    const parts = changed.map((field) =>
      field === "priority" || field === "goal"
        ? `${FIELD_LABELS[field]}: ${before[field as keyof StoryInput]} → ${after[field as keyof StoryInput]}`
        : `${FIELD_LABELS[field]} changed`,
    );
    return `"${after.goal}": ${parts.join("; ") || "no visible change"}`;
  }
  const goals = (stories: StoryInput[]) => stories.map((s) => `"${s.goal}"`).join(", ");
  return `${goals(change.before) || "—"} → ${goals(change.after) || "removed"}`;
}

function ChangeLog({ changes }: { changes: StoryChange[] }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-xl font-semibold">Change log</h2>
      {changes.length === 0 ? (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">No changes yet.</p>
      ) : (
        <ol className="flex flex-col gap-2 text-sm">
          {changes.map((change) => (
            <li key={change.id} className="rounded-md bg-neutral-100 p-3 dark:bg-neutral-900">
              <p className="font-medium">
                {ACTION_LABELS[change.action]} by {change.changed_by} ·{" "}
                {dateTimeFormat.format(new Date(change.created_at))}
              </p>
              <p className="text-neutral-600 dark:text-neutral-300">{describeChange(change)}</p>
              {change.note && <p className="mt-1">Reason: {change.note}</p>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
