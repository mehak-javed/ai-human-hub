import { Suspense } from "react";

import { AdminProjectReview } from "@/components/AdminProjectReview";
import { RequireSignIn } from "@/components/RequireSignIn";

export default function AdminProjectPage({ params }: PageProps<"/admin/projects/[id]">) {
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-12">
      <Suspense fallback={<p>Loading…</p>}>
        <RequireSignIn>
          <ReviewFromParams params={params} />
        </RequireSignIn>
      </Suspense>
    </main>
  );
}

async function ReviewFromParams({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <AdminProjectReview id={id} />;
}
