import { Suspense } from "react";

import { AdminProjectList } from "@/components/AdminProjectList";
import { RequireSignIn } from "@/components/RequireSignIn";
import { TeamNav } from "@/components/TeamNav";

export default function AdminPage() {
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-12">
      <h1 className="text-3xl font-semibold">Team review</h1>
      <TeamNav current="review" />
      <Suspense fallback={<p>Loading…</p>}>
        <RequireSignIn>
          <AdminProjectList />
        </RequireSignIn>
      </Suspense>
    </main>
  );
}
