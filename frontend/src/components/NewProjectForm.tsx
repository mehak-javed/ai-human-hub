"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, createProject, PROJECT_TYPES, type ProjectType } from "@/lib/api";

type FieldErrors = Partial<Record<"name" | "project_type" | "consent", string[]>>;

export function NewProjectForm() {
  const { getToken } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [projectType, setProjectType] = useState<ProjectType>("website");
  const [consent, setConsent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setErrors({});
    setFormError(null);

    try {
      const token = await getToken();
      if (!token) {
        setFormError("Your session has expired. Please sign in again.");
        return;
      }
      const project = await createProject(token, { name, project_type: projectType, consent });
      router.push(`/projects/${project.id}`);
    } catch (error: unknown) {
      if (error instanceof ApiError && error.status === 400) {
        setErrors(error.body as FieldErrors);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
      <div className="flex flex-col gap-1">
        <label htmlFor="name" className="font-medium">
          Project name
        </label>
        <input
          id="name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={120}
          required
          aria-invalid={Boolean(errors.name)}
          aria-describedby={errors.name ? "name-error" : undefined}
          className="rounded-md border border-neutral-300 bg-transparent px-3 py-2 dark:border-neutral-700"
        />
        {errors.name && (
          <p id="name-error" className="text-sm text-red-600">
            {errors.name.join(" ")}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="project_type" className="font-medium">
          What are we building?
        </label>
        <select
          id="project_type"
          value={projectType}
          onChange={(event) => setProjectType(event.target.value as ProjectType)}
          className="rounded-md border border-neutral-300 bg-transparent px-3 py-2 dark:border-neutral-700"
        >
          {Object.entries(PROJECT_TYPES).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        {errors.project_type && (
          <p className="text-sm text-red-600">{errors.project_type.join(" ")}</p>
        )}
      </div>

      <fieldset className="flex flex-col gap-3 rounded-lg border border-neutral-300 p-4 dark:border-neutral-700">
        <legend className="px-1 font-medium">Before you record</legend>
        <ul className="list-disc pl-5 text-sm text-neutral-700 dark:text-neutral-300">
          <li>Your voice recording is turned into text and the audio is deleted straight away.</li>
          <li>Names, emails, phone numbers and addresses are hidden before any AI sees the text.</li>
          <li>We keep the text and your approved user stories for up to 12 months.</li>
          <li>You can ask us to delete your project and its data at any time.</li>
        </ul>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
            aria-describedby={errors.consent ? "consent-error" : undefined}
            className="mt-1"
          />
          <span>I have read this notice and agree to my voice being recorded and transcribed.</span>
        </label>
        {errors.consent && (
          <p id="consent-error" className="text-sm text-red-600">
            {errors.consent.join(" ")}
          </p>
        )}
      </fieldset>

      {formError && (
        <p role="alert" className="text-sm text-red-600">
          {formError}
        </p>
      )}

      <button
        type="submit"
        disabled={!consent || submitting}
        className="w-fit rounded-md bg-neutral-900 px-4 py-2 font-medium text-white disabled:opacity-50 dark:bg-white dark:text-neutral-900"
      >
        {submitting ? "Creating…" : "Start project"}
      </button>
    </form>
  );
}