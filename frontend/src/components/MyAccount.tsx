"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import { getMe, type Me } from "@/lib/api";

type State = { kind: "loading" } | { kind: "loaded"; me: Me } | { kind: "error" };

export function MyAccount() {
  const { getToken, isLoaded } = useAuth();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    if (!isLoaded) {
      return;
    }
    const controller = new AbortController();

    async function load() {
      try {
        const token = await getToken();
        if (!token) {
          setState({ kind: "error" });
          return;
        }
        const me = await getMe(token, controller.signal);
        setState({ kind: "loaded", me });
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState({ kind: "error" });
      }
    }

    load();
    return () => controller.abort();
  }, [getToken, isLoaded]);

  if (state.kind === "loading") {
    return <p role="status">Checking your account with the API…</p>;
  }
  if (state.kind === "error") {
    return <p role="status">Could not load your account from the API.</p>;
  }
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg border border-neutral-300 p-4 text-sm dark:border-neutral-700">
      <dt className="font-medium">API user ID</dt>
      <dd>{state.me.id}</dd>
      <dt className="font-medium">Clerk ID</dt>
      <dd className="break-all">{state.me.clerk_id}</dd>
      <dt className="font-medium">Role</dt>
      <dd>{state.me.role}</dd>
    </dl>
  );
}