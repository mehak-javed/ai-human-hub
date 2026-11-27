import { Suspense } from "react";

import { AuditLog } from "@/components/AuditLog";
import { RequireSignIn } from "@/components/RequireSignIn";
import { TeamNav } from "@/components/TeamNav";

export default function AuditPage() {
  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-12">
      <h1 className="text-3xl font-semibold">Audit log</h1>
      <TeamNav current="audit" />
      <Suspense fallback={<p>Loading…</p>}>
        <RequireSignIn>
          <AuditLog />
        </RequireSignIn>
      </Suspense>
    </main>
  );
}
