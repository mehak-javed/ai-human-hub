"use client";

import { useCallback, useState } from "react";

import {
  buttonClass,
  EMPTY_STORY,
  ErrorText,
  inputClass,
  primaryClass,
  PRIORITY_ORDER,
  StoryForm,
  StoryText,
  useAction,
} from "@/components/story-ui";
import {
  addStory,
  approveStories,
  editStory,
  listStories,
  type Project,
  removeStory,
  reviseStories,
  STORY_PRIORITIES,
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
      <StoryText story={story} />
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
