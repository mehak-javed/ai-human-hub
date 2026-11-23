import { Suspense } from "react";

import { ProjectDetail } from "@/components/ProjectDetail";
import { RequireSignIn } from "@/components/RequireSignIn";

export default function ProjectPage({ params }: PageProps<"/projects/[id]">) {
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-12">
      <Suspense fallback={<p>Loading…</p>}>
        <RequireSignIn>
          <ProjectFromParams params={params} />
        </RequireSignIn>
      </Suspense>
    </main>
  );
}

async function ProjectFromParams({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProjectDetail id={id} />;
}