"use client";

import { useEffect, useState } from "react";

import { getHealth } from "@/lib/api";

type Status = "checking" | "up" | "down";

const LABELS: Record<Status, string> = {
  checking: "Checking backend…",
  up: "Backend is up",
  down: "Backend is unreachable",
};

const DOT_COLOURS: Record<Status, string> = {
  checking: "bg-neutral-400",
  up: "bg-green-500",
  down: "bg-red-500",
};

export function BackendStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    const controller = new AbortController();

    getHealth(controller.signal)
      .then((data) => setStatus(data.status === "ok" ? "up" : "down"))
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setStatus("down");
      });

    return () => controller.abort();
  }, []);

  return (
    <p
      role="status"
      className="inline-flex w-fit items-center gap-2 rounded-full border border-neutral-300 px-3 py-1 text-sm dark:border-neutral-700"
    >
      <span className={`h-2 w-2 rounded-full ${DOT_COLOURS[status]}`} aria-hidden="true" />
      {LABELS[status]}
    </p>
  );
}