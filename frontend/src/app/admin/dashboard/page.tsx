import { Suspense } from "react";

import { RequireSignIn } from "@/components/RequireSignIn";
import { TeamDashboard } from "@/components/TeamDashboard";
import { TeamNav } from "@/components/TeamNav";

export default function DashboardPage() {
  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-12">
      <h1 className="text-3xl font-semibold">Team dashboard</h1>
      <TeamNav current="dashboard" />
      <Suspense fallback={<p>Loading…</p>}>
        <RequireSignIn>
          <TeamDashboard />
        </RequireSignIn>
      </Suspense>
    </main>
  );
}
