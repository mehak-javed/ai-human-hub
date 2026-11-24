"use client";

import { useCallback, useState } from "react";

import { Recorder } from "@/components/Recorder";
import { listTranscripts, type Project, type Transcript } from "@/lib/api";
import { useApi } from "@/lib/useApi";

// N2: 15 minutes of audio per interview; one recording is at most 10 minutes.
const INTERVIEW_LIMIT_SECONDS = 15 * 60;
const RECORDING_LIMIT_SECONDS = 10 * 60;

const timeFormat = new Intl.DateTimeFormat("en-GB", { timeStyle: "short" });

export function Transcripts({ project }: { project: Project }) {
  const load = useCallback(
    (token: string, signal: AbortSignal) => listTranscripts(token, project.id, signal),
    [project.id],
  );
  const state = useApi(load);
  const [added, setAdded] = useState<Transcript[]>([]);

  if (state.kind === "loading") {
    return <p role="status">Loading your recordings…</p>;
  }
  if (state.kind === "error") {
    return <p role="status">Could not load your recordings.</p>;
  }

  const transcripts = [...state.data, ...added];
  const usedSeconds = transcripts.reduce((total, t) => total + (t.duration_seconds ?? 0), 0);
  const remainingSeconds = Math.floor(INTERVIEW_LIMIT_SECONDS - usedSeconds);
  const canRecord = project.status === "interviewing" && remainingSeconds > 0;

  return (
    <div className="flex flex-col gap-6">
      {canRecord ? (
        <Recorder
          projectId={project.id}
          maxSeconds={Math.min(RECORDING_LIMIT_SECONDS, remainingSeconds)}
          onTranscribed={(transcript) => setAdded((current) => [...current, transcript])}
        />
      ) : (
        project.status === "interviewing" && (
          <p>You&apos;ve used the full 15 minutes of recording time for this interview.</p>
        )
      )}

      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">What you&apos;ve told us</h2>
        {transcripts.length === 0 ? (
          <p className="text-neutral-600 dark:text-neutral-300">
            Nothing yet. Your words will appear here as text after each recording.
          </p>
        ) : (
          <ol className="flex flex-col gap-3">
            {transcripts.map((transcript) => (
              <li
                key={transcript.id}
                className="rounded-lg border border-neutral-300 p-4 dark:border-neutral-700"
              >
                <p className="whitespace-pre-wrap">{transcript.text}</p>
                <details className="mt-3 text-sm">
                  <summary className="cursor-pointer text-neutral-600 dark:text-neutral-300">
                    What our AI will see
                  </summary>
                  <p className="mt-2 whitespace-pre-wrap rounded-md bg-neutral-100 p-3 dark:bg-neutral-900">
                    {transcript.masked_text}
                  </p>
                  <p className="mt-1 text-xs text-neutral-500">
                    Names, emails, phone numbers and addresses are hidden before any AI reads your
                    words.
                  </p>
                </details>
                <p className="mt-2 text-xs text-neutral-500">
                  Recorded at {timeFormat.format(new Date(transcript.created_at))}
                </p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}