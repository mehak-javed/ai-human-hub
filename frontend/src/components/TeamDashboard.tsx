"use client";

import {
  BarList,
  ChartCard,
  ColumnChart,
  formatNumber,
  Legend,
  type Part,
  SegmentedBar,
  SERIES,
  StatTile,
} from "@/components/charts";
import { getDashboard, type ProjectStatus, STORY_PRIORITIES } from "@/lib/api";
import { useApi } from "@/lib/useApi";

const weekFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
const dayFormat = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });

const STAGES: { key: ProjectStatus; label: string }[] = [
  { key: "interviewing", label: "Interviewing" },
  { key: "awaiting_client", label: "Awaiting client" },
  { key: "awaiting_admin", label: "Awaiting our review" },
  { key: "sent_to_github", label: "Sent to GitHub" },
];

const FEATURES: Record<string, string> = {
  transcription: "Transcription",
  follow_up_questions: "Follow-up questions",
  user_stories: "User stories",
};

function percent(share: number | null): string {
  return share === null ? "–" : `${Math.round(share * 100)}%`;
}

/** The team's dashboard (A2, A7, A9, AI7). */
export function TeamDashboard() {
  const state = useApi(getDashboard);

  if (state.kind === "loading") return <p role="status">Loading the dashboard…</p>;
  if (state.kind === "error") {
    return <p role="status">{state.status === 403 ? "This page is only for our team." : "Could not load the dashboard."}</p>;
  }

  const { overview, interviews_by_week, stories_by_priority, projects_by_client, ai_quality, ai_usage } = state.data;
  const limit = ai_usage.workers_ai_daily_neurons;
  const today = ai_usage.days[ai_usage.days.length - 1];

  const qualityParts: Part[] = [
    { key: "unchanged", label: "Accepted unchanged", value: ai_quality.accepted_unchanged },
    { key: "client", label: "Changed by the client", value: ai_quality.edited_by_client },
    { key: "team", label: "Edited by our team", value: ai_quality.edited_by_team },
    { key: "removed", label: "Merged, split or rejected", value: ai_quality.removed_by_team },
  ];

  return (
    <div className="flex flex-col gap-6">
      {ai_usage.warnings.length > 0 && (
        <div role="alert" className="flex flex-col gap-1 rounded-lg border border-amber-500 bg-amber-50 p-4 text-sm text-amber-950 dark:bg-amber-950 dark:text-amber-50">
          {ai_usage.warnings.map((warning) => (
            <p key={warning}>
              <span aria-hidden>⚠️ </span>
              <strong>Warning:</strong> {warning}
            </p>
          ))}
        </div>
      )}

      {/* A2: the business at a glance. */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Active clients" value={formatNumber(overview.active_clients)} note="last 30 days" />
        <StatTile label="Interviews this week" value={formatNumber(overview.interviews_this_week)} />
        <StatTile label="Stories created" value={formatNumber(overview.stories_created)} />
        <StatTile label="Issues pushed" value={formatNumber(overview.issues_pushed)} note="to GitHub" />
      </div>

      {/* AI7: how good is the AI? */}
      <ChartCard
        title="AI stories accepted unchanged"
        subtitle="In projects the client has approved"
        table={{
          columns: ["Outcome", "Stories"],
          rows: qualityParts.map((p) => [p.label, p.value]),
        }}
      >
        <p className="text-4xl font-semibold tabular-nums">{percent(ai_quality.acceptance_rate)}</p>
        {ai_quality.ai_stories > 0 ? (
          <>
            <Legend parts={qualityParts} />
            <SegmentedBar parts={qualityParts} ariaLabel="What happened to the AI's stories" />
          </>
        ) : (
          <p className="text-sm" style={{ color: "var(--viz-text-2)" }}>
            No approved projects yet.
          </p>
        )}
      </ChartCard>

      {/* A7: AI usage against the free limits. */}
      <ChartCard
        title="Workers AI usage per day"
        subtitle={`Neurons used, against the free limit of ${formatNumber(limit)} a day. Today: ${formatNumber(
          today.workers_ai_neurons,
        )} (${percent(limit ? today.workers_ai_neurons / limit : null)}).`}
        table={{
          columns: ["Day", "Workers AI neurons", "Groq calls"],
          rows: ai_usage.days.map((d) => [dayFormat.format(new Date(d.day)), d.workers_ai_neurons, d.groq_calls]),
        }}
      >
        <ColumnChart
          ariaLabel="Workers AI neurons used per day over the last 14 days"
          data={ai_usage.days.map((d) => ({
            label: dayFormat.format(new Date(d.day)),
            value: d.workers_ai_neurons,
            tooltip: `${dayFormat.format(new Date(d.day))}: ${formatNumber(d.workers_ai_neurons)} neurons, ${d.groq_calls} Groq calls`,
          }))}
          references={
            // Only draw the limit lines once usage is close enough to matter,
            // so small daily numbers aren't squashed flat.
            ai_usage.days.some((d) => d.workers_ai_neurons >= limit * 0.5)
              ? [
                  { value: limit, label: "Free limit", tone: "limit" },
                  { value: limit * ai_usage.warning_share, label: "80% warning", tone: "warning" },
                ]
              : []
          }
        />
        {ai_usage.groq_today.length > 0 ? (
          <div className="text-sm" style={{ color: "var(--viz-text-2)" }}>
            <p className="font-medium" style={{ color: "var(--viz-text)" }}>
              Groq (backup) today
            </p>
            <ul>
              {ai_usage.groq_today.map((g) => (
                <li key={g.feature}>
                  {FEATURES[g.feature] ?? g.feature}: {g.calls} calls
                  {g.request_limit !== null &&
                    g.requests_remaining !== null &&
                    `, ${formatNumber(g.requests_remaining)} of ${formatNumber(g.request_limit)} requests left`}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-sm" style={{ color: "var(--viz-text-2)" }}>
            Groq (backup) hasn&apos;t been needed today.
          </p>
        )}
      </ChartCard>

      <div className="grid gap-6 md:grid-cols-2">
        {/* A9: interviews over time. */}
        <ChartCard
          title="New interviews per week"
          subtitle="Last 12 weeks"
          table={{
            columns: ["Week starting", "Interviews"],
            rows: interviews_by_week.map((w) => [weekFormat.format(new Date(w.week)), w.count]),
          }}
        >
          <ColumnChart
            narrow
            ariaLabel="New interviews per week over the last 12 weeks"
            data={interviews_by_week.map((w) => ({
              label: weekFormat.format(new Date(w.week)),
              value: w.count,
              tooltip: `Week of ${weekFormat.format(new Date(w.week))}: ${w.count} ${w.count === 1 ? "interview" : "interviews"}`,
            }))}
          />
        </ChartCard>

        {/* A9: stories by priority. */}
        <ChartCard
          title="Stories by priority"
          subtitle="All current stories"
          table={{
            columns: ["Priority", "Stories"],
            rows: stories_by_priority.map((p) => [STORY_PRIORITIES[p.priority], p.count]),
          }}
        >
          <BarList data={stories_by_priority.map((p) => ({ label: STORY_PRIORITIES[p.priority], value: p.count }))} />
        </ChartCard>
      </div>

      {/* A9: progress per client. */}
      <ChartCard
        title="Projects per client, by stage"
        subtitle="Busiest clients first"
        table={{
          columns: ["Client", ...STAGES.map((s) => s.label)],
          rows: projects_by_client.map((c) => [c.client, ...STAGES.map((s) => c.by_status[s.key])]),
        }}
      >
        {projects_by_client.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--viz-text-2)" }}>
            No projects yet.
          </p>
        ) : (
          <>
            <Legend parts={STAGES.map((s) => ({ key: s.key, label: s.label, value: 0 }))} />
            <ul className="flex flex-col gap-2">
              {projects_by_client.map((c) => {
                const widest = Math.max(...projects_by_client.map((x) => x.total));
                return (
                  <li key={c.client} className="grid grid-cols-[9rem_1fr] items-center gap-3 text-sm">
                    <span className="truncate" style={{ color: "var(--viz-text-2)" }} title={c.client}>
                      {c.client}
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="flex h-4 gap-[2px]" style={{ width: `${(c.total / widest) * 85}%` }}>
                        {STAGES.map((s, i) =>
                          c.by_status[s.key] ? (
                            <span
                              key={s.key}
                              className="h-full first:rounded-l last:rounded-r"
                              style={{ flexGrow: c.by_status[s.key], flexBasis: 0, background: SERIES[i] }}
                              title={`${c.client}, ${s.label}: ${c.by_status[s.key]}`}
                            />
                          ) : null,
                        )}
                      </span>
                      <span className="tabular-nums">{c.total}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </ChartCard>
    </div>
  );
}
