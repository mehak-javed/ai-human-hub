"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { buttonClass, ErrorText, useAction } from "@/components/story-ui";
import { deleteProject, downloadRequirements, type Project } from "@/lib/api";

/** Download the approved requirements (P4) and delete the project (C11). */
export function ProjectActions({ project }: { project: Project }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const download = useAction();
  const remove = useAction();
  const approved = project.status === "awaiting_admin" || project.status === "sent_to_github";

  return (
    <section className="flex flex-col gap-3 border-t border-neutral-200 pt-6 dark:border-neutral-800">
      <h2 className="text-xl font-semibold">Your data</h2>

      {approved && (
        <div className="flex flex-col items-start gap-1">
          <button
            type="button"
            disabled={download.busy}
            onClick={() =>
              download.run(async (token) => {
                const { blob, filename } = await downloadRequirements(token, project.id);
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = filename;
                link.click();
                URL.revokeObjectURL(url);
              })
            }
            className={buttonClass}
          >
            {download.busy ? "Preparing…" : "Download requirements (Markdown)"}
          </button>
          <ErrorText error={download.error} />
        </div>
      )}

      {confirming ? (
        <div className="flex flex-col items-start gap-2 rounded-lg border border-red-300 p-4 text-sm dark:border-red-900">
          <p>
            Delete <strong>{project.name}</strong>? Your recordings&apos; text, answers and stories
            are removed straight away and can&apos;t be recovered.
            {project.status === "sent_to_github" &&
              " Issues already in your GitHub repository stay there."}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={remove.busy}
              onClick={() =>
                remove.run(async (token) => {
                  await deleteProject(token, project.id);
                  router.push("/dashboard");
                })
              }
              className="rounded-md bg-red-600 px-4 py-2 font-medium text-white disabled:opacity-50"
            >
              {remove.busy ? "Deleting…" : "Yes, delete everything"}
            </button>
            <button type="button" disabled={remove.busy} onClick={() => setConfirming(false)} className={buttonClass}>
              Keep my project
            </button>
          </div>
          <ErrorText error={remove.error} />
        </div>
      ) : (
        <button type="button" onClick={() => setConfirming(true)} className="self-start text-sm text-red-600 underline">
          Delete project
        </button>
      )}
    </section>
  );
}
