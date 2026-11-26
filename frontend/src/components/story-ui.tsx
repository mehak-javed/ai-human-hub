"use client";

import { useAuth } from "@clerk/nextjs";
import { type FormEvent, useState } from "react";

import {
  ApiError,
  type Progress,
  type StoryInput,
  STORY_PRIORITIES,
  type StoryPriority,
  type UserStory,
} from "@/lib/api";

// Shared by the client's review (Stories) and our team's review (AdminProjectReview).

export const PRIORITY_ORDER: StoryPriority[] = ["must", "should", "nice"];

export const buttonClass =
  "rounded-md border border-neutral-300 px-4 py-2 font-medium disabled:opacity-50 dark:border-neutral-700";
export const primaryClass =
  "rounded-md bg-neutral-900 px-4 py-2 font-medium text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900";
export const inputClass =
  "rounded-md border border-neutral-300 p-2 text-base dark:border-neutral-700 dark:bg-neutral-950";

// Words whose first letter is misleading: "a user", "a one-off buyer", "an hour".
const SOUNDS_LIKE_CONSONANT = /^(?:u(?:s|ni|ti|r[aeiou])|eu|one\b|once\b)/i;
const SOUNDS_LIKE_VOWEL = /^(?:hour|honest|honou?r|heir)/i;

/** "a patient", "an admin", "a user", "an hourly worker": by sound, not spelling. */
export function withArticle(role: string): string {
  const word = role.trim();
  const an = SOUNDS_LIKE_VOWEL.test(word) || (!SOUNDS_LIKE_CONSONANT.test(word) && /^[aeiou]/i.test(word));
  return `${an ? "an" : "a"} ${role}`;
}

export function errorMessage(error: unknown): string {
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
export function useAction() {
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

export function ErrorText({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p role="alert" className="text-sm text-red-600">
      {error}
    </p>
  );
}

/** "As a patient, I want to …, so that …" with its acceptance criteria. */
export function StoryText({ story }: { story: UserStory }) {
  return (
    <>
      {story.github_issue_closed && (
        <p className="mb-1 inline-block rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-900 dark:bg-green-950 dark:text-green-200">
          ✓ Built{story.github_issue_number ? ` (issue #${story.github_issue_number} closed)` : ""}
        </p>
      )}
      <p>
        As {withArticle(story.role)}, I want to <strong>{story.goal}</strong>, so that{" "}
        {story.reason.replace(/\.$/, "")}.
      </p>
      <ul className="mt-2 list-disc pl-5 text-sm text-neutral-600 dark:text-neutral-300">
        {story.acceptance_criteria.map((criterion, index) => (
          <li key={index}>{criterion}</li>
        ))}
      </ul>
    </>
  );
}

export const EMPTY_STORY: StoryInput = {
  role: "",
  goal: "",
  reason: "",
  acceptance_criteria: [],
  priority: "should",
};

/** A story being edited; acceptance criteria are typed one per line. */
export type StoryDraft = {
  role: string;
  goal: string;
  reason: string;
  criteria: string;
  priority: StoryPriority;
};

export function toDraft(story: StoryInput): StoryDraft {
  return {
    role: story.role,
    goal: story.goal,
    reason: story.reason,
    criteria: story.acceptance_criteria.join("\n"),
    priority: story.priority,
  };
}

export function fromDraft(draft: StoryDraft): StoryInput {
  return {
    role: draft.role.trim(),
    goal: draft.goal.trim(),
    reason: draft.reason.trim(),
    // One criterion per line; blank lines are ignored.
    acceptance_criteria: draft.criteria
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean),
    priority: draft.priority,
  };
}

/** The inputs for one story. Controlled, so several can share one form. */
export function StoryFields({
  value,
  onChange,
}: {
  value: StoryDraft;
  onChange: (draft: StoryDraft) => void;
}) {
  const set = (changes: Partial<StoryDraft>) => onChange({ ...value, ...changes });
  return (
    <>
      <label className="flex flex-col gap-1">
        As a…
        <input
          value={value.role}
          onChange={(e) => set({ role: e.target.value })}
          required
          maxLength={80}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1">
        I want to…
        <input
          value={value.goal}
          onChange={(e) => set({ goal: e.target.value })}
          required
          maxLength={300}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1">
        So that…
        <input
          value={value.reason}
          onChange={(e) => set({ reason: e.target.value })}
          required
          maxLength={300}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1">
        How we&apos;ll know it works (one per line)
        <textarea
          value={value.criteria}
          onChange={(e) => set({ criteria: e.target.value })}
          required
          rows={3}
          className={inputClass}
        />
      </label>
      <label className="flex flex-col gap-1">
        Priority
        <select
          value={value.priority}
          onChange={(e) => set({ priority: e.target.value as StoryPriority })}
          className={inputClass}
        >
          {PRIORITY_ORDER.map((priority) => (
            <option key={priority} value={priority}>
              {STORY_PRIORITIES[priority]}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}

/** Buttons and error message at the bottom of a story form. */
export function FormButtons({
  submitLabel,
  onCancel,
  busy,
  error,
}: {
  submitLabel: string;
  onCancel: () => void;
  busy: boolean;
  error: string | null;
}) {
  return (
    <>
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={busy} className={primaryClass}>
          {busy ? "Saving…" : submitLabel}
        </button>
        <button type="button" onClick={onCancel} disabled={busy} className={buttonClass}>
          Cancel
        </button>
      </div>
      <ErrorText error={error} />
    </>
  );
}

export function StoryForm({
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
  const [draft, setDraft] = useState(() => toDraft(initial));

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit(fromDraft(draft));
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 text-sm">
      <StoryFields value={draft} onChange={setDraft} />
      <FormButtons submitLabel={submitLabel} onCancel={onCancel} busy={busy} error={error} />
    </form>
  );
}

const timeFormat = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

/** C10: how much is built, from closed GitHub issues. */
export function ProgressBar({ progress }: { progress: Progress }) {
  const { done, total } = progress;
  const percent = total ? Math.round((done / total) * 100) : 0;
  return (
    <section
      aria-labelledby="progress-heading"
      className="viz-root flex flex-col gap-2 rounded-lg border p-4"
      style={{ background: "var(--viz-surface)", borderColor: "var(--viz-grid)", color: "var(--viz-text)" }}
    >
      <h2 id="progress-heading" className="font-semibold">
        Progress
      </h2>
      <p className="text-2xl font-semibold tabular-nums">
        {done} of {total} features built <span className="text-base font-normal">({percent}%)</span>
      </p>
      <div
        role="progressbar"
        aria-label="Features built"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        aria-valuetext={`${done} of ${total} features built`}
        className="h-3 w-full overflow-hidden rounded"
        style={{ background: "var(--viz-grid)" }}
      >
        <div
          className="h-full rounded"
          style={{ width: `${percent}%`, minWidth: done ? 4 : 0, background: "var(--viz-series-1)" }}
        />
      </div>
      <p className="text-xs" style={{ color: "var(--viz-muted)" }}>
        A feature counts as built when its GitHub issue is closed.
        {progress.synced_at && ` Checked with GitHub ${timeFormat.format(new Date(progress.synced_at))}.`}
      </p>
    </section>
  );
}
