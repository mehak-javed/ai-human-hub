import { auth } from "@clerk/nextjs/server";
import { Suspense } from "react";

import { MyAccount } from "@/components/MyAccount";

export default function DashboardPage() {
  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 px-4 py-12">
      <h1 className="text-3xl font-semibold">Your dashboard</h1>
      <Suspense fallback={<p>Loading…</p>}>
        <SignedInOnly />
      </Suspense>
    </main>
  );
}

async function SignedInOnly() {
  const { isAuthenticated, redirectToSignIn } = await auth();
  if (!isAuthenticated) {
    return redirectToSignIn();
  }

  return (
    <>
      <p className="text-neutral-600 dark:text-neutral-300">
        Your projects will appear here.
      </p>
      <MyAccount />
    </>
  );
}