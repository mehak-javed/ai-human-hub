"use client";

import { type FormEvent, useState } from "react";

import { buttonClass, ErrorText, inputClass, primaryClass, useAction } from "@/components/story-ui";
import { type AdminProjectDetail, ApiError, connectGitHubRepo, type SendResult, sendToGitHub } from "@/lib/api";

const dateTimeFormat = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" });

/** Connect a private repo and send the reviewed stories to it (A5, A6). */
export function GitHubDelivery({ project, onChanged }: { project: AdminProjectDetail; onChanged: () => void }) {
  const sent = project.status === "sent_to_github";

  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-xl font-semibold">GitHub</h2>

      {!project.github.configured ? (
        <p className="rounded-md bg-neutral-100 p-3 text-sm dark:bg-neutral-900">
          Our GitHub App isn&apos;t set up yet, so nothing can be sent. Add its ID and private key to
          the API&apos;s environment variables.
        </p>
      ) : (
        <>
          {!sent && <ConnectRepo project={project} onConnected={onChanged} />}
          {project.github_repo && (
            <p className="text-sm">
              Repository:{" "}
              <a href={`https://github.com/${project.github_repo}`} className="underline" target="_blank" rel="noreferrer">
                {project.github_repo}
              </a>
              {sent && project.sent_to_github_at && ` · sent ${dateTimeFormat.format(new Date(project.sent_to_github_at))}`}
            </p>
          )}
          {project.status === "awaiting_admin" && project.github_repo && (
            <SendButton project={project} onSent={onChanged} />
          )}
        </>
      )}

      {project.pushes.length > 0 && (
        <ol className="flex flex-col gap-2 text-sm">
          {project.pushes.map((push) => (
            <li key={push.id} className="rounded-md bg-neutral-100 p-3 dark:bg-neutral-900">
              <p className="font-medium">
                {push.status === "succeeded" ? "Sent" : push.status === "failed" ? "Failed" : "Sending"} by{" "}
                {push.pushed_by} · {dateTimeFormat.format(new Date(push.started_at))}
              </p>
              <p className="text-neutral-600 dark:text-neutral-300">
                {push.issues_created} issues created, {push.issues_updated} updated
                {push.commit_url && (
                  <>
                    {" · "}
                    <a href={push.commit_url} className="underline" target="_blank" rel="noreferrer">
                      requirements.md commit
                    </a>
                  </>
                )}
              </p>
              {push.error && <p className="mt-1 text-red-600">{push.error}</p>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function ConnectRepo({ project, onConnected }: { project: AdminProjectDetail; onConnected: () => void }) {
  const [repo, setRepo] = useState(project.github_repo);
  const { busy, error, run } = useAction();

  function submit(event: FormEvent) {
    event.preventDefault();
    run(async (token) => {
      await connectGitHubRepo(token, project.id, repo.trim());
      onConnected();
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2 text-sm">
      <label className="flex flex-col gap-1">
        Private repository (owner/name)
        <input
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          placeholder="acme/bakery-website"
          required
          maxLength={140}
          className={inputClass}
        />
      </label>
      {project.github.install_url && (
        <p className="text-neutral-600 dark:text-neutral-300">
          The repository must be private and have our GitHub App installed.{" "}
          <a href={project.github.install_url} className="underline" target="_blank" rel="noreferrer">
            Install the App
          </a>
        </p>
      )}
      <button type="submit" disabled={busy || !repo.trim()} className={`${buttonClass} self-start`}>
        {busy ? "Testing the connection…" : project.github_repo ? "Change repository" : "Connect repository"}
      </button>
      <ErrorText error={error} />
    </form>
  );
}

function SendButton({ project, onSent }: { project: AdminProjectDetail; onSent: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const { busy, error, run } = useAction();

  async function send() {
    await run(async (token) => {
      try {
        await sendToGitHub(token, project.id);
      } catch (err) {
        // A failed push is recorded and shown in the list below.
        if (err instanceof ApiError && err.status === 502 && (err.body as SendResult | null)?.push) {
          onSent();
          return;
        }
        throw err;
      }
      onSent();
    });
  }

  return (
    <div className="flex flex-col items-start gap-2 rounded-lg bg-neutral-100 p-4 text-sm dark:bg-neutral-900">
      {confirming ? (
        <>
          <p>
            Send {project.stories.length} stories to {project.github_repo}? Each becomes an issue, and
            requirements.md is committed. The stories are then locked.
          </p>
          <div className="flex gap-2">
            <button type="button" disabled={busy} onClick={send} className={primaryClass}>
              {busy ? "Sending…" : "Yes, send to GitHub"}
            </button>
            <button type="button" disabled={busy} onClick={() => setConfirming(false)} className={buttonClass}>
              Not yet
            </button>
          </div>
        </>
      ) : (
        <button type="button" onClick={() => setConfirming(true)} className={primaryClass}>
          Send to GitHub
        </button>
      )}
      <ErrorText error={error} />
    </div>
  );
}
