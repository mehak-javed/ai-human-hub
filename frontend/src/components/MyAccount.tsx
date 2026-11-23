"use client";

import { getMe } from "@/lib/api";
import { useApi } from "@/lib/useApi";

export function MyAccount() {
  const state = useApi(getMe);

  if (state.kind === "loading") {
    return <p role="status">Checking your account with the API…</p>;
  }
  if (state.kind === "error") {
    return <p role="status">Could not load your account from the API.</p>;
  }
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg border border-neutral-300 p-4 text-sm dark:border-neutral-700">
      <dt className="font-medium">API user ID</dt>
      <dd>{state.data.id}</dd>
      <dt className="font-medium">Clerk ID</dt>
      <dd className="break-all">{state.data.clerk_id}</dd>
      <dt className="font-medium">Role</dt>
      <dd>{state.data.role}</dd>
    </dl>
  );
}