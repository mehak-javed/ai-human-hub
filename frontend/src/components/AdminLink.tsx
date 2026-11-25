"use client";

import Link from "next/link";

import { getMe } from "@/lib/api";
import { useApi } from "@/lib/useApi";

/** A header link to the team's review pages, shown only to admins. */
export function AdminLink() {
  const state = useApi(getMe);
  // The API decides who is an admin; this only hides a link the others
  // couldn't use anyway.
  if (state.kind !== "loaded" || state.data.role !== "admin") {
    return null;
  }
  return <Link href="/admin">Team review</Link>;
}
