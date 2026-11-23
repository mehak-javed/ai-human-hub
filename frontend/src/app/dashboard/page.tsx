import Link from "next/link";
import { Suspense } from "react";

import { MyAccount } from "@/components/MyAccount";
import { ProjectList } from "@/components/ProjectList";
import { RequireSignIn } from "@/components/RequireSignIn";

export default function DashboardPage() {
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-12">
      <h1 className="text-3xl font-semibold">Your dashboard</h1>
      <Suspense fallback={<p>Loading…</p>}>
        <RequireSignIn>
          <section className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold">Your projects</h2>
              <Link
                href="/projects/new"
                className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white dark:bg-white dark:text-neutral-900"
              >
                New project
              </Link>
            </div>
            <ProjectList />
          </section>
          <section className="flex flex-col gap-2">
            <h2 className="text-xl font-semibold">Your account</h2>
            <MyAccount />
          </section>
        </RequireSignIn>
      </Suspense>
    </main>
  );
}