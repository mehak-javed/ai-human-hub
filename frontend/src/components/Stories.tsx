"use client";

import { useAuth } from "@clerk/nextjs";
import { type FormEvent, useCallback, useState } from "react";

import {
  addStory,
  ApiError,
  approveStories,
  editStory,
  listStories,
  type Project,
  removeStory,
  reviseStories,
  type StoryInput,
  STORY_PRIORITIES,
  type StoryPriority,
  type UserStory,
  writeStories,
} from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Props = {
  project: Project;
  /** Stories can only be written once the client has recorded something. */
  hasTranscripts: boolean;
  onProjectChange: (project: Project) => void;
};

const PRIORITY_ORDER: StoryPriority[] = ["must", "should", "nice"];

const buttonClass =
  "rounded-md border border-neutral-300 px-4 py-2 font-medium disabled:opacity-50 dark:border-neutral-700";
const primaryClass =
  "rounded-md bg-neutral-900 px-4 py-2 font-medium text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900";
const inputClass =
  "rounded-md border border-neutral-300 p-2 text-base dark:border-neutral-700 dark:bg-neutral-950";

/** "a patient", "an admin". */
function withArticle(role: string): string {
  return `${/^[aeiou]/i.test(role) ? "an" : "a"} ${role}`;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as Record<string, unknown> | null;
    if (typeof body?.detail === "string") return body.detail;
    if (error.status === 429) return "You've asked our AI a lot. Please wait a while and try again.";
    if (error.status === 400 && body) return "Please check the highlighted story and try again.";
    return `Something went wrong. Please try again (error ${error.status}).`;
  }
  return "Something went wrong. Please try again.";
}

/** Run an API call with a fresh token, tracking busy and error state. */
function useAction() {
  const { getToken } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(call: (token: string) => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) {
        setError("Your session has expired. Please sign in again.");
        return;
      }
      await call(token);
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return { busy, error, run };
}

function ErrorText({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p role="alert" className="text-sm text-red-600">
      {error}
    </p>
  );
}

export function Stories({ project, hasTranscripts, onProjectChange }: Props) {
  const load = useCallback(
    (token: string, signal: AbortSignal) => listStories(token, project.id, signal),
    [project.id],
  );
  const state = useApi(load);
  // Changes made in this visit replace the stories loaded with the page.
  const [changed, setChanged] = useState<UserStory[] | null>(null);

  if (state.kind === "loading") {
    return <p role="status">Loading your user stories…</p>;
  }
  if (state.kind === "error") {
    return <p role="status">Could not load your user stories.</p>;
  }

  const stories = changed ?? state.data;
  const reviewing = project.status === "awaiting_client";

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-xl font-semibold">Your user stories</h2>

      {project.status === "interviewing" && (
        <WriteStories
          project={project}
          hasTranscripts={hasTranscripts}
          onWritten={(written) => {
            setChanged(written);
            onProjectChange({ ...project, status: "awaiting_client" });
          }}
        />
      )}

      {reviewing && (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          Written by AI from the masked version of your words. Change anything that isn&apos;t
          right, add what&apos;s missing, then approve them.
        </p>
      )}
      {(project.status === "awaiting_admin" || project.status === "sent_to_github") && (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          You approved these stories. Our team is reviewing them now.
        </p>
      )}

      {stories.length > 0 &&
        PRIORITY_ORDER.map((priority) => {
          const group = stories.filter((story) => story.priority === priority);
          if (group.length === 0) return null;
          return (
            <div key={priority} className="flex flex-col gap-3">
              <h3 className="font-semibold">
                {STORY_PRIORITIES[priority]} ({group.length})
              </h3>
              <ul className="flex flex-col gap-3">
                {group.map((story) => (
                  <StoryCard
                    key={story.id}
                    projectId={project.id}
                    story={story}
                    editable={reviewing}
                    onSaved={(saved) =>
                      setChanged(stories.map((s) => (s.id === saved.id ? saved : s)))
                    }
                    onRemoved={() => setChanged(stories.filter((s) => s.id !== story.id))}
                  />
                ))}
              </ul>
            </div>
          );
        })}

      {reviewing && (
        <>
          <AddStory
            projectId={project.id}
            onAdded={(added) => setChanged([...stories, added])}
          />
          <ReviseStories projectId={project.id} onRevised={setChanged} />
          <ApproveStories
            projectId={project.id}
            storyCount={stories.length}
            onApproved={onProjectChange}
          />
        </>
      )}
    </section>
  );
}

function WriteStories({
  project,
  hasTranscripts,
  onWritten,
}: {
  project: Project;
  hasTranscripts: boolean;
  onWritten: (stories: UserStory[]) => void;
}) {
  const { busy, error, run } = useAction();

  if (!hasTranscripts) {
    return (
      <p className="text-neutral-600 dark:text-neutral-300">
        Record your explanation first. Then our AI can turn it into user stories.
      </p>
    );
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <p className="text-neutral-600 dark:text-neutral-300">
        When you&apos;ve finished explaining and answered our questions, our AI will turn your words
        into user stories. You can then review and change them, but not record any more.
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={() => run(async (token) => onWritten(await writeStories(token, project.id)))}
        className={primaryClass}
      >
        {busy ? "Writing…" : "Finish and write my user stories"}
      </button>
      {busy && (
        <p role="status" className="text-sm text-neutral-600 dark:text-neutral-300">
          Our AI is reading what you said and writing your stories. This can take up to a minute.
        </p>
      )}
      <ErrorText error={error} />
    </div>
  );
}

function StoryCard({
  projectId,
  story,
  editable,
  onSaved,
  onRemoved,
}: {
  projectId: number;
  story: UserStory;
  editable: boolean;
  onSaved: (story: UserStory) => void;
  onRemoved: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const { busy, error, run } = useAction();

  if (editing) {
    return (
      <li className="rounded-lg border border-neutral-300 p-4 dark:border-neutral-700">
        <StoryForm
          initial={story}
          submitLabel="Save changes"
          onCancel={() => setEditing(false)}
          onSubmit={(input) =>
            run(async (token) => {
              onSaved(await editStory(token, projectId, story.id, input));
              setEditing(false);
            })
          }
          busy={busy}
          error={error}
        />
      </li>
    );
  }

  return (
    <li className="rounded-lg border border-neutral-300 p-4 dark:border-neutral-700">
      <p>
        As {withArticle(story.role)}, I want to <strong>{story.goal}</strong>, so that{" "}
        {story.reason.replace(/\.$/, "")}.
      </p>
      <ul className="mt-2 list-disc pl-5 text-sm text-neutral-600 dark:text-neutral-300">
        {story.acceptance_criteria.map((criterion, index) => (
          <li key={index}>{criterion}</li>
        ))}
      </ul>
      {(story.origin === "client" || story.client_edited) && (
        <p className="mt-2 text-xs text-neutral-500">
          {story.origin === "client" ? "Added by you" : "Changed by you"}
        </p>
      )}
      {editable && (
        <div className="mt-3 flex gap-3 text-sm">
          <button type="button" onClick={() => setEditing(true)} className="underline">
            Edit
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(async (token) => {
                await removeStory(token, projectId, story.id);
                onRemoved();
              })
            }
            className="text-red-600 underline disabled:opacity-50"
          >
            {busy ? "Removing…" : "Remove"}
          </button>
        </div>
      )}
      <ErrorText error={editing ? null : error} />
    </li>
  );
}

const EMPTY_STORY: StoryInput = {
  role: "",
  goal: "",
  reason: "",
  acceptance_criteria: [],
  priority: "should",
};

function StoryForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
  busy,
  error,
}: {
  initial: StoryInput;
  submitLabel: string;
  onSubmit: (story: StoryInput) => void;
  onCancel: () => void;
  busy: boolean;
  error: string | null;
}) {
  const [role, setRole] = useState(initial.role);
  const [goal, setGoal] = useState(initial.goal);
  const [reason, setReason] = useState(initial.reason);
  const [criteria, setCriteria] = useState(initial.acceptance_criteria.join("\n"));
  const [priority, setPriority] = useState<StoryPriority>(initial.priority);

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit({
      role: role.trim(),
      goal: goal.trim(),
      reason: reason.trim(),
      // One criterion per line; blank lines are ignored.
      acceptance_criteria: criteria
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
      priority,
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 text-sm">
      <label className="flex flex-col gap-1">
        As a…
        <input
          value={role}
          onChange={(e) => setRole(e.target.value)}
          required
          maxLength={80}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1">
        I want to…
        <input
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          required
          maxLength={300}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1">
        So that…
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          required
          maxLength={300}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1">
        How we&apos;ll know it works (one per line)
        <textarea
          value={criteria}
          onChange={(e) => setCriteria(e.target.value)}
          required
          rows={3}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1">
        Priority
        <select
          value={priority}
          onChange={(e) => setPriority(e.target.value as StoryPriority)}
          className={inputClass}
        >
          {PRIORITY_ORDER.map((value) => (
            <option key={value} value={value}>
              {STORY_PRIORITIES[value]}
            </option>
          ))}
        </select>
      </label>
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy} className={primaryClass}>
          {busy ? "Saving…" : submitLabel}
        </button>
        <button type="button" onClick={onCancel} disabled={busy} className={buttonClass}>
          Cancel
        </button>
      </div>
      <ErrorText error={error} />
    </form>
  );
}

function AddStory({ projectId, onAdded }: { projectId: number; onAdded: (story: UserStory) => void }) {
  const [open, setOpen] = useState(false);
  const { busy, error, run } = useAction();

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className={`${buttonClass} self-start`}>
        Add a missing story
      </button>
    );
  }

  return (
    <div className="rounded-lg border border-dashed border-neutral-400 p-4">
      <h3 className="mb-3 font-semibold">Add a missing story</h3>
      <StoryForm
        initial={EMPTY_STORY}
        submitLabel="Add story"
        onCancel={() => setOpen(false)}
        onSubmit={(input) =>
          run(async (token) => {
            onAdded(await addStory(token, projectId, input));
            setOpen(false);
          })
        }
        busy={busy}
        error={error}
      />
    </div>
  );
}

function ReviseStories({
  projectId,
  onRevised,
}: {
  projectId: number;
  onRevised: (stories: UserStory[]) => void;
}) {
  const [note, setNote] = useState("");
  const { busy, error, run } = useAction();

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        run(async (token) => {
          onRevised(await reviseStories(token, projectId, note.trim()));
          setNote("");
        });
      }}
      className="flex flex-col gap-2 rounded-lg border border-neutral-300 p-4 text-sm dark:border-neutral-700"
    >
      <label className="flex flex-col gap-1">
        <span className="font-semibold">Ask our AI to change them</span>
        Tell us what&apos;s wrong, for example &quot;Customers don&apos;t need accounts&quot;. Your
        own changes above are kept.
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          maxLength={1000}
          className={inputClass}
        />
      </label>
      <button type="submit" disabled={busy || !note.trim()} className={`${buttonClass} self-start`}>
        {busy ? "Rewriting…" : "Rewrite my stories"}
      </button>
      <ErrorText error={error} />
    </form>
  );
}

function ApproveStories({
  projectId,
  storyCount,
  onApproved,
}: {
  projectId: number;
  storyCount: number;
  onApproved: (project: Project) => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const { busy, error, run } = useAction();

  return (
    <div className="flex flex-col items-start gap-2 rounded-lg bg-neutral-100 p-4 dark:bg-neutral-900">
      {confirming ? (
        <>
          <p>
            Approve these {storyCount} stories? They&apos;ll be locked and sent to our team, and you
            won&apos;t be able to change them.
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => run(async (token) => onApproved(await approveStories(token, projectId)))}
              className={primaryClass}
            >
              {busy ? "Approving…" : "Yes, approve"}
            </button>
            <button type="button" onClick={() => setConfirming(false)} disabled={busy} className={buttonClass}>
              Not yet
            </button>
          </div>
        </>
      ) : (
        <button
          type="button"
          disabled={storyCount === 0}
          onClick={() => setConfirming(true)}
          className={primaryClass}
        >
          Approve my stories
        </button>
      )}
      <ErrorText error={error} />
    </div>
  );
}
