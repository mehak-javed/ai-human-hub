"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api";

export type ApiState<T> =
  | { kind: "loading" }
  | { kind: "loaded"; data: T }
  | { kind: "error"; status?: number };

/**
 * Load data from our API as the signed-in user.
 *
 * `load` receives a fresh Clerk session token and an abort signal. Pass a
 * function that doesn't change between renders (define it outside the
 * component, or wrap it in useCallback).
 */
export function useApi<T>(load: (token: string, signal: AbortSignal) => Promise<T>): ApiState<T> {
  const { getToken, isLoaded } = useAuth();
  const [state, setState] = useState<ApiState<T>>({ kind: "loading" });

  useEffect(() => {
    if (!isLoaded) {
      return;
    }
    const controller = new AbortController();

    async function run() {
      try {
        const token = await getToken();
        if (!token) {
          setState({ kind: "error", status: 401 });
          return;
        }
        const data = await load(token, controller.signal);
        setState({ kind: "loaded", data });
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setState({ kind: "error", status: error instanceof ApiError ? error.status : undefined });
      }
    }

    run();
    return () => controller.abort();
  }, [getToken, isLoaded, load]);

  return state;
}