"use client";

import { type ReactNode, useState } from "react";

// Small, dependency-free charts for the team dashboard.
//
// Colours come from the --viz-* tokens in globals.css (validated for colour-
// blind readers in light and dark mode). Rules followed throughout: one
// y-axis, thin bars with 4px rounded ends, a 2px gap between touching
// segments, text in text colours (never the series colour), a hover tooltip
// on every mark, and a table view for every chart.

export const SERIES = ["var(--viz-series-1)", "var(--viz-series-2)", "var(--viz-series-3)", "var(--viz-series-4)"];

const number = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });
const compact = new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 1 });

export function formatNumber(value: number): string {
  return Math.abs(value) >= 10_000 ? compact.format(value) : number.format(value);
}

/** A rounded-up axis maximum and evenly spaced ticks: 0, 250, 500… */
function niceTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0, 1];
  const rough = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= rough) ?? rough;
  const top = Math.ceil(max / step) * step;
  return Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
}

export function ChartCard({
  title,
  subtitle,
  children,
  table,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  /** The same numbers as a table: needed for screen readers and low-contrast colours. */
  table: { columns: string[]; rows: (string | number)[][] };
}) {
  return (
    <section
      className="viz-root flex flex-col gap-3 rounded-lg border p-4"
      style={{ background: "var(--viz-surface)", borderColor: "var(--viz-grid)", color: "var(--viz-text)" }}
    >
      <header>
        <h3 className="font-semibold">{title}</h3>
        {subtitle && (
          <p className="text-sm" style={{ color: "var(--viz-text-2)" }}>
            {subtitle}
          </p>
        )}
      </header>
      {children}
      <details className="text-sm" style={{ color: "var(--viz-text-2)" }}>
        <summary className="cursor-pointer">Show as a table</summary>
        <table className="mt-2 w-full text-left">
          <thead>
            <tr>
              {table.columns.map((column) => (
                <th key={column} className="py-1 pr-4 font-medium">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i} className="border-t" style={{ borderColor: "var(--viz-grid)" }}>
                {row.map((cell, j) => (
                  <td key={j} className="py-1 pr-4 tabular-nums">
                    {typeof cell === "number" ? formatNumber(cell) : cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}

export function StatTile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div
      className="viz-root flex flex-col gap-1 rounded-lg border p-4"
      style={{ background: "var(--viz-surface)", borderColor: "var(--viz-grid)", color: "var(--viz-text)" }}
    >
      <span className="text-sm" style={{ color: "var(--viz-text-2)" }}>
        {label}
      </span>
      <span className="text-3xl font-semibold tabular-nums">{value}</span>
      {note && (
        <span className="text-xs" style={{ color: "var(--viz-muted)" }}>
          {note}
        </span>
      )}
    </div>
  );
}

/** Positioned over the chart with CSS percentages, so it follows the SVG's scaling. */
function Tooltip({ left, top, children }: { left: string; top: string; children: ReactNode }) {
  return (
    <div
      role="tooltip"
      className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md px-2 py-1 text-xs shadow"
      style={{ left, top, marginTop: -8, background: "var(--viz-text)", color: "var(--viz-surface)", whiteSpace: "nowrap" }}
    >
      {children}
    </div>
  );
}

/** A path for a bar with 4px rounded ends at the data end, square at the baseline. */
function columnPath(x: number, y: number, width: number, height: number): string {
  const r = Math.min(4, width / 2, height);
  return `M${x},${y + height} V${y + r} Q${x},${y} ${x + r},${y} H${x + width - r} Q${x + width},${y} ${
    x + width
  },${y + r} V${y + height} Z`;
}

export type Column = { label: string; value: number; tooltip: string };
export type Reference = { value: number; label: string; tone: "limit" | "warning" };

/** Vertical columns for one series over time, with optional limit lines. */
export function ColumnChart({
  data,
  references = [],
  ariaLabel,
  narrow = false,
}: {
  data: Column[];
  references?: Reference[];
  ariaLabel: string;
  /** For half-width cards: draws on a smaller canvas so text stays readable. */
  narrow?: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const width = narrow ? 340 : 640;
  const height = narrow ? 180 : 200;
  const left = 44;
  const bottom = 24;
  const top = 12;
  const plotWidth = width - left - 8;
  const plotHeight = height - top - bottom;
  const max = Math.max(...data.map((d) => d.value), ...references.map((r) => r.value), 0);
  const ticks = niceTicks(max);
  const yMax = ticks[ticks.length - 1];
  const band = plotWidth / data.length;
  const barWidth = Math.min(24, band * 0.6);
  const y = (value: number) => top + plotHeight - (value / yMax) * plotHeight;
  // Label every other column when there are many, so labels never collide.
  const labelEvery = Math.ceil(data.length / (narrow ? 4 : 8));

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label={ariaLabel}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={left} x2={width - 8} y1={y(tick)} y2={y(tick)} stroke="var(--viz-grid)" strokeWidth={1} />
            <text x={left - 6} y={y(tick)} dy="0.32em" textAnchor="end" fontSize={11} fill="var(--viz-muted)">
              {formatNumber(tick)}
            </text>
          </g>
        ))}
        {data.map((d, i) => {
          const x = left + i * band + (band - barWidth) / 2;
          const barHeight = (d.value / yMax) * plotHeight;
          return (
            <g key={d.label}>
              {d.value > 0 && (
                <path
                  d={columnPath(x, y(d.value), barWidth, barHeight)}
                  fill="var(--viz-series-1)"
                  opacity={hover === null || hover === i ? 1 : 0.55}
                />
              )}
              {i % labelEvery === 0 && (
                <text x={x + barWidth / 2} y={height - 6} textAnchor="middle" fontSize={11} fill="var(--viz-muted)">
                  {d.label}
                </text>
              )}
              {/* A hit target the full height of the band, bigger than the bar. */}
              <rect
                x={left + i * band}
                y={top}
                width={band}
                height={plotHeight}
                fill="transparent"
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
            </g>
          );
        })}
        <line x1={left} x2={width - 8} y1={y(0)} y2={y(0)} stroke="var(--viz-axis)" strokeWidth={1} />
        {references.map((ref) => (
          <g key={ref.label}>
            <line
              x1={left}
              x2={width - 8}
              y1={y(ref.value)}
              y2={y(ref.value)}
              stroke={ref.tone === "limit" ? "var(--viz-critical)" : "var(--viz-warning)"}
              strokeWidth={1.5}
            />
            {/* Labelled at the left, away from the newest (rightmost) columns. */}
            <text x={left + 4} y={y(ref.value) - 4} textAnchor="start" fontSize={11} fill="var(--viz-text-2)">
              {ref.label}
            </text>
          </g>
        ))}
      </svg>
      {hover !== null && (
        <Tooltip
          left={`${((left + hover * band + band / 2) / width) * 100}%`}
          top={`${(y(data[hover].value) / height) * 100}%`}
        >
          {data[hover].tooltip}
        </Tooltip>
      )}
    </div>
  );
}

/** Horizontal bars for one series across categories, value at the tip. */
export function BarList({ data }: { data: { label: string; value: number }[] }) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <ul className="flex flex-col gap-2">
      {data.map((d) => (
        <li key={d.label} className="grid grid-cols-[7rem_1fr] items-center gap-3 text-sm" title={`${d.label}: ${formatNumber(d.value)}`}>
          <span style={{ color: "var(--viz-text-2)" }}>{d.label}</span>
          <span className="flex items-center gap-2">
            <span
              className="h-4 rounded-r"
              style={{ width: `${(d.value / max) * 85}%`, minWidth: d.value ? 4 : 0, background: "var(--viz-series-1)" }}
            />
            <span className="tabular-nums">{formatNumber(d.value)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export type Part = { key: string; label: string; value: number };

export function Legend({ parts }: { parts: Part[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm" style={{ color: "var(--viz-text-2)" }}>
      {parts.map((part, i) => (
        <li key={part.key} className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: SERIES[i] }} aria-hidden />
          {part.label}
        </li>
      ))}
    </ul>
  );
}

/** One whole split into parts, 2px surface gap between them, hover for values. */
export function SegmentedBar({ parts, ariaLabel }: { parts: Part[]; ariaLabel: string }) {
  const [hover, setHover] = useState<string | null>(null);
  const total = parts.reduce((sum, p) => sum + p.value, 0);
  if (total === 0) return null;
  const shown = parts.find((p) => p.key === hover);
  return (
    <div className="flex flex-col gap-1">
      <div className="flex h-4 w-full gap-[2px]" role="img" aria-label={ariaLabel}>
        {parts.map((part, i) =>
          part.value === 0 ? null : (
            <span
              key={part.key}
              className="h-full first:rounded-l last:rounded-r"
              style={{ flexGrow: part.value, flexBasis: 0, background: SERIES[i], opacity: hover && hover !== part.key ? 0.55 : 1 }}
              onMouseEnter={() => setHover(part.key)}
              onMouseLeave={() => setHover(null)}
            />
          ),
        )}
      </div>
      <p className="h-5 text-xs" style={{ color: "var(--viz-text-2)" }}>
        {shown && `${shown.label}: ${formatNumber(shown.value)} of ${formatNumber(total)}`}
      </p>
    </div>
  );
}
