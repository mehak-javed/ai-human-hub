import Link from "next/link";

/** Switch between the team's pages. */
export function TeamNav({ current }: { current: "review" | "dashboard" | "audit" }) {
  const item = (href: string, label: string, active: boolean) => (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={active ? "font-semibold underline underline-offset-4" : "text-neutral-600 dark:text-neutral-300"}
    >
      {label}
    </Link>
  );
  return (
    <nav className="flex gap-4 text-sm">
      {item("/admin", "Projects to review", current === "review")}
      {item("/admin/dashboard", "Dashboard", current === "dashboard")}
      {item("/admin/audit", "Audit log", current === "audit")}
    </nav>
  );
}
