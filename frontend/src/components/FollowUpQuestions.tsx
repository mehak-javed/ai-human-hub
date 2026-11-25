"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useState } from "react";

import { Recorder } from "@/components/Recorder";
import {
  answerQuestion,
  answerQuestionByVoice,
  ApiError,
  askQuestions,
  type FollowUpQuestion,
  listQuestions,
  type Project,
  QUESTION_TOPICS,
} from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Props = {
  project: Project;
  /** The AI can only look for gaps once the client has recorded something. */
  hasTranscripts: boolean;
};

// A spoken answer is short: at most two minutes.
const VOICE_ANSWER_SECONDS = 2 * 60;

const buttonClass =
  "rounded-md border border-neutral-300 px-4 py-2 font-medium disabled:opacity-50 dark:border-neutral-700";
const primaryClass =
  "rounded-md bg-neutral-900 px-4 py-2 font-medium text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const body = error.body as { detail?: string; non_field_errors?: string[] } | null;
    if (body?.detail) return body.detail;
    if (body?.non_field_errors) return body.non_field_errors.join(" ");
    return `Something went wrong. Please try again (error ${error.status}).`;
  }
  return "Something went wrong. Please try again.";
}

export function FollowUpQuestions({ project, hasTranscripts }: Props) {
  const load = useCallback(
    (token: string, signal: AbortSignal) => listQuestions(token, project.id, signal),
    [project.id],
  );
  const state = useApi(load);
  // Changes made in this visit replace the list loaded with the page.
  const [changed, setChanged] = useState<FollowUpQuestion[] | null>(null);

  if (state.kind === "loading") {
    return <p role="status">Loading follow-up questions…</p>;
  }
  if (state.kind === "error") {
    return <p role="status">Could not load your follow-up questions.</p>;
  }

  const questions = changed ?? state.data;
  const canChange = project.status === "interviewing";
  // Once the interview has ended, there is nothing to ask any more.
  if (questions.length === 0 && !canChange) {
    return null;
  }

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-xl font-semibold">A few questions</h2>
      {questions.length === 0 ? (
        <AskForQuestions
          project={project}
          canAsk={canChange && hasTranscripts}
          hasTranscripts={hasTranscripts}
          asked={changed !== null}
          onAsked={setChanged}
        />
      ) : (
        <QuestionList
          projectId={project.id}
          questions={questions}
          canAnswer={canChange}
          onAnswered={(updated) =>
            setChanged(questions.map((q) => (q.id === updated.id ? updated : q)))
          }
        />
      )}
    </section>
  );
}

function AskForQuestions({
  project,
  canAsk,
  hasTranscripts,
  asked,
  onAsked,
}: {
  project: Project;
  canAsk: boolean;
  hasTranscripts: boolean;
  asked: boolean;
  onAsked: (questions: FollowUpQuestion[]) => void;
}) {
  const { getToken } = useAuth();
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (asked) {
    return <p>You covered everything we needed. You can write your user stories now.</p>;
  }
  if (!hasTranscripts) {
    return (
      <p className="text-neutral-600 dark:text-neutral-300">
        After your recording, our AI will check whether anything important is missing.
      </p>
    );
  }

  async function ask() {
    setAsking(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) {
        setError("Your session has expired. Please sign in again.");
        return;
      }
      onAsked(await askQuestions(token, project.id));
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <p className="text-neutral-600 dark:text-neutral-300">
        When you&apos;ve finished explaining, our AI will check for missing details, such as who
        will use it, payments or deadlines, and ask you about them one at a time.
      </p>
      {canAsk && (
        <button type="button" onClick={ask} disabled={asking} className={primaryClass}>
          {asking ? "Checking…" : "Check for missing details"}
        </button>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}

function QuestionList({
  projectId,
  questions,
  canAnswer,
  onAnswered,
}: {
  projectId: number;
  questions: FollowUpQuestion[];
  canAnswer: boolean;
  onAnswered: (question: FollowUpQuestion) => void;
}) {
  // The question the client chose to change; otherwise the first open one.
  const [chosenId, setChosenId] = useState<number | null>(null);
  const done = questions.filter((q) => q.status !== "open").length;
  const current =
    questions.find((q) => q.id === chosenId) ?? questions.find((q) => q.status === "open") ?? null;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-neutral-600 dark:text-neutral-300">
        {done} of {questions.length} answered
      </p>

      {current && canAnswer ? (
        <CurrentQuestion
          // A new key resets the typed answer when the question changes.
          key={current.id}
          projectId={projectId}
          question={current}
          number={questions.indexOf(current) + 1}
          total={questions.length}
          onAnswered={(updated) => {
            setChosenId(null);
            onAnswered(updated);
          }}
        />
      ) : (
        done === questions.length && (
          <p>Thank you, that&apos;s everything. You can write your user stories now.</p>
        )
      )}

      {done > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-neutral-600 dark:text-neutral-300">
            Your answers
          </summary>
          <ol className="mt-2 flex flex-col gap-2">
            {questions
              .filter((q) => q.status !== "open")
              .map((q) => (
                <li key={q.id} className="rounded-md bg-neutral-100 p-3 dark:bg-neutral-900">
                  <p className="font-medium">{q.question}</p>
                  <p className="whitespace-pre-wrap">{q.status === "not_sure" ? "Not sure" : q.answer}</p>
                  {canAnswer && (
                    <button
                      type="button"
                      onClick={() => setChosenId(q.id)}
                      className="mt-1 text-xs underline"
                    >
                      Change
                    </button>
                  )}
                </li>
              ))}
          </ol>
        </details>
      )}
    </div>
  );
}

function CurrentQuestion({
  projectId,
  question,
  number,
  total,
  onAnswered,
}: {
  projectId: number;
  question: FollowUpQuestion;
  number: number;
  total: number;
  onAnswered: (question: FollowUpQuestion) => void;
}) {
  const { getToken } = useAuth();
  const [text, setText] = useState(question.answer);
  const [byVoice, setByVoice] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(answer: string | null) {
    setSaving(true);
    setError(null);
    try {
      const token = await getToken();
      if (!token) {
        setError("Your session has expired. Please sign in again.");
        return;
      }
      onAnswered(await answerQuestion(token, projectId, question.id, answer));
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-neutral-300 p-4 dark:border-neutral-700">
      <p className="text-xs uppercase tracking-wide text-neutral-500">
        Question {number} of {total} · {QUESTION_TOPICS[question.topic]}
      </p>
      <p className="text-lg font-medium">{question.question}</p>

      {byVoice ? (
        <Recorder
          maxSeconds={VOICE_ANSWER_SECONDS}
          title="Say your answer"
          hint="Press Record and answer in your own words."
          send={async (token, audio) => {
            onAnswered(await answerQuestionByVoice(token, projectId, question.id, audio));
          }}
        />
      ) : (
        <>
          <label className="flex flex-col gap-1 text-sm">
            Your answer
            <textarea
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={3}
              maxLength={2000}
              className="rounded-md border border-neutral-300 p-2 text-base dark:border-neutral-700 dark:bg-neutral-950"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => save(text)}
              disabled={saving || !text.trim()}
              className={primaryClass}
            >
              {saving ? "Saving…" : "Save answer"}
            </button>
            <button type="button" onClick={() => save(null)} disabled={saving} className={buttonClass}>
              Not sure
            </button>
          </div>
        </>
      )}

      <button
        type="button"
        onClick={() => setByVoice((current) => !current)}
        className="self-start text-sm underline"
      >
        {byVoice ? "Type my answer instead" : "Answer by voice instead"}
      </button>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}