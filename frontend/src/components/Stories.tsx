"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useState } from "react";

import {
  ApiError,
  listStories,
  type Project,
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
};

const PRIORITY_ORDER: StoryPriority[] = ["must", "should", "nice"];

/** "a patient", "an admin". */
function withArticle(role: string): string {
  return `${/^[aeiou]/i.test(role) ? "an" : "a"} ${role}`;
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as { detail?: string } | null;
    if (body?.detail) return body.detail;
    if (error.status === 429) return "You've asked for new stories a lot. Please wait a while and try again.";
    return `Something went wrong writing your stories. Please try again (error ${error.status}).`;
  }
  return "Something went wrong writing your stories. Please try again.";
}

export function Stories({ project, hasTranscripts }: Props) {
  const { getToken } = useAuth();
  const load = useCallback(
    (token: string, signal: AbortSignal) => listStories(token, project.id, signal),
    [project.id],
  );
  const state = useApi(load);
  // Stories written in this visit replace the ones loaded with the page.
  const [written, setWritten] = useState<UserStory[] | null>(null);
  const [writing, setWriting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (state.kind === "loading") {
    return <p role="status">Loading your user stories…</p>;
  }
  if (state.kind === "error") {
    return <p role="status">Could not load your user stories.</p>;
  }

  const stories = written ?? state.data;
  const canWrite = project.status === "interviewing" && hasTranscripts;

  async function write() {
    setWriting(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) {
        setError("Your session has expired. Please sign in again.");
        return;
      }
      setWritten(await writeStories(token, project.id));
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setWriting(false);
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xl font-semibold">Your user stories</h2>
        {canWrite && (
          <button
            type="button"
            onClick={write}
            disabled={writing}
            className="rounded-md bg-neutral-900 px-4 py-2 font-medium text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900"
          >
            {writing ? "Writing…" : stories.length > 0 ? "Rewrite my stories" : "Write my user stories"}
          </button>
        )}
      </div>

      {writing && (
        <p role="status" className="text-sm text-neutral-600 dark:text-neutral-300">
          Our AI is reading what you said and writing your stories. This can take up to a minute.
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      {stories.length === 0 ? (
        <p className="text-neutral-600 dark:text-neutral-300">
          {hasTranscripts
            ? "When you've finished explaining, press the button and our AI will turn your words into user stories."
            : "Record your explanation first. Then our AI can turn it into user stories."}
        </p>
      ) : (
        <>
          <p className="text-sm text-neutral-600 dark:text-neutral-300">
            Written by AI from the masked version of your words. You&apos;ll be able to review and
            change them before anything is built.
          </p>
          {PRIORITY_ORDER.map((priority) => {
            const group = stories.filter((story) => story.priority === priority);
            if (group.length === 0) return null;
            return (
              <div key={priority} className="flex flex-col gap-3">
                <h3 className="font-semibold">
                  {STORY_PRIORITIES[priority]} ({group.length})
                </h3>
                <ul className="flex flex-col gap-3">
                  {group.map((story) => (
                    <li
                      key={story.id}
                      className="rounded-lg border border-neutral-300 p-4 dark:border-neutral-700"
                    >
                      <p>
                        As {withArticle(story.role)}, I want to <strong>{story.goal}</strong>, so
                        that {story.reason.replace(/\.$/, "")}.
                      </p>
                      <ul className="mt-2 list-disc pl-5 text-sm text-neutral-600 dark:text-neutral-300">
                        {story.acceptance_criteria.map((criterion, index) => (
                          <li key={index}>{criterion}</li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </>
      )}
    </section>
  );
}