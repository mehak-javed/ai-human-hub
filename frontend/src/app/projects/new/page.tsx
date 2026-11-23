import { Suspense } from "react";

import { NewProjectForm } from "@/components/NewProjectForm";
import { RequireSignIn } from "@/components/RequireSignIn";

export default function NewProjectPage() {
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-12">
      <h1 className="text-3xl font-semibold">Start a new project</h1>
      <Suspense fallback={<p>Loading…</p>}>
        <RequireSignIn>
          <NewProjectForm />
        </RequireSignIn>
      </Suspense>
    </main>
  );
}