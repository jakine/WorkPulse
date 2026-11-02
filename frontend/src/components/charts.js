import { useState } from "react";
import { styles } from "./ui";

// Status keeps its own reserved colors and always shows an icon and a label.
export const STATUS = {
  done: { label: "Done", color: "var(--status-good)", icon: "check" },
  on_track: { label: "On track", color: "var(--status-good)", icon: "check" },
  behind: { label: "Behind", color: "var(--status-warning)", icon: "alert" },
  stalled: { label: "Stalled", color: "var(--status-critical)", icon: "pause" },
  not_started: { label: "Not started", color: "var(--muted)", icon: "dot" },
  no_plan: { label: "No planned end", color: "var(--muted)", icon: "dot" },
  no_scopes: { label: "No work lines", color: "var(--muted)", icon: "dot" },
};

function StatusIcon({ icon, color }) {
  const common = { width: 12, height: 12, viewBox: "0 0 12 12", "aria-hidden": true, style: { flex: "none" } };
  if (icon === "check") {
    return (
      <svg {...common}>
        <path d="M2.5 6.5l2.2 2.2 4.8-5" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (icon === "alert") {
    return (
      <svg {...common}>
        <path d="M6 1.2l5 9.3H1z" fill={color} />
        <path d="M6 4.5v2.6" stroke="#1b1814" strokeWidth="1.4" strokeLinecap="round" />
        <circle cx="6" cy="8.9" r="0.75" fill="#1b1814" />
      </svg>
    );
  }
  if (icon === "pause") {
    return (
      <svg {...common}>
        <rect x="2.5" y="2" width="2.4" height="8" rx="1" fill={color} />
        <rect x="7.1" y="2" width="2.4" height="8" rx="1" fill={color} />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <circle cx="6" cy="6" r="3.5" fill="none" stroke={color} strokeWidth="1.6" />
    </svg>
  );
}

export function StatusBadge({ status }) {
  const meta = STATUS[status] || STATUS.no_plan;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.35rem",
        padding: "0.1rem 0.55rem",
        borderRadius: "999px",
        border: "1px solid var(--line)",
        background: "var(--surface-2)",
        color: "var(--ink)",
        fontSize: "0.75rem",
        fontWeight: 600,
        whiteSpace: "nowrap",
      }}
    >
      <StatusIcon icon={meta.icon} color={meta.color} />
      {meta.label}
    </span>
  );
}

export function ProgressMeter({ percent, status, label }) {
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  const color = (STATUS[status] || STATUS.on_track).color;
  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
      style={{
        height: "8px",
        borderRadius: "4px",
        background: `color-mix(in srgb, ${color} 18%, var(--surface))`,
        overflow: "hidden",
      }}
    >
      <div style={{ width: `${value}%`, height: "100%", borderRadius: "4px", background: color }} />
    </div>
  );
}

const VIEW_W = 320;
const VIEW_H = 150;
const PAD = { top: 18, right: 8, bottom: 22, left: 34 };

function niceStep(max) {
  if (max <= 0) return 1;
  const rough = max / 3;
  const power = 10 ** Math.floor(Math.log10(rough));
  return [1, 2, 2.5, 5, 10].find((multiple) => multiple * power >= rough) * power;
}

function compact(value) {
  if (value >= 10000) return `${Math.round(value / 1000)}K`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function columnPath(x, y, width, height) {
  const r = Math.min(4, height, width / 2);
  return `M${x},${y + height}V${y + r}Q${x},${y} ${x + r},${y}H${x + width - r}Q${x + width},${y} ${x + width},${y + r}V${y + height}Z`;
}

function weekLabel(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** One series of weekly totals as columns. The title names the series, so there is no legend. */
export function WeeklyColumns({ title, unit, weeks }) {
  const [active, setActive] = useState(null);
  const values = weeks.map((row) => Number(row.quantity) || 0);
  const max = Math.max(0, ...values);
  const step = niceStep(max);
  const top = Math.max(step, Math.ceil(max / step) * step);
  const ticks = [];
  for (let tick = 0; tick <= top + step / 1000; tick += step) ticks.push(tick);
  const plotW = VIEW_W - PAD.left - PAD.right;
  const plotH = VIEW_H - PAD.top - PAD.bottom;
  const band = plotW / Math.max(weeks.length, 1);
  const barW = Math.min(24, band * 0.62);
  const y = (value) => PAD.top + plotH - (value / top) * plotH;
  const last = weeks.length - 1;

  return (
    <figure style={{ margin: 0, display: "grid", gap: "0.35rem", minWidth: 0 }}>
      <figcaption style={{ fontSize: "0.85rem", fontWeight: 600 }}>{title}</figcaption>
      {max === 0 ? (
        <p style={{ margin: 0, color: "var(--muted)", fontSize: "0.85rem" }}>No work reported in these weeks.</p>
      ) : (
        <div style={{ position: "relative", maxWidth: `${VIEW_W}px` }}>
          <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} width="100%" role="img" aria-label={`${title}, weekly totals in ${unit}`}>
            {ticks.map((tick) => (
              <g key={tick}>
                <line x1={PAD.left} x2={VIEW_W - PAD.right} y1={y(tick)} y2={y(tick)} stroke="var(--line)" strokeWidth="1" />
                <text
                  x={PAD.left - 6}
                  y={y(tick)}
                  textAnchor="end"
                  dominantBaseline="middle"
                  fontSize="10"
                  fill="var(--muted)"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {compact(tick)}
                </text>
              </g>
            ))}
            {weeks.map((row, index) => {
              const value = values[index];
              const x = PAD.left + band * index + (band - barW) / 2;
              const height = PAD.top + plotH - y(value);
              return (
                <g key={row.week}>
                  {value > 0 && (
                    <path
                      d={columnPath(x, y(value), barW, height)}
                      fill="var(--accent)"
                      opacity={active === null || active === index ? 1 : 0.55}
                    />
                  )}
                  {index === last && (
                    <text x={x + barW / 2} y={y(value) - 5} textAnchor="middle" fontSize="10.5" fontWeight="600" fill="var(--ink)">
                      {compact(value)}
                    </text>
                  )}
                  {(last - index) % 2 === 0 && (
                    <text x={x + barW / 2} y={VIEW_H - 6} textAnchor="middle" fontSize="10" fill="var(--muted)">
                      {weekLabel(row.week)}
                    </text>
                  )}
                  <rect
                    x={PAD.left + band * index}
                    y={PAD.top}
                    width={band}
                    height={plotH}
                    fill="transparent"
                    tabIndex={0}
                    aria-label={`Week of ${weekLabel(row.week)}: ${row.quantity} ${unit}`}
                    onMouseEnter={() => setActive(index)}
                    onMouseLeave={() => setActive(null)}
                    onFocus={() => setActive(index)}
                    onBlur={() => setActive(null)}
                    style={{ outline: "none" }}
                  />
                </g>
              );
            })}
          </svg>
          {active !== null && (
            <div
              role="status"
              style={{
                position: "absolute",
                top: 0,
                left: `${((PAD.left + band * (active + 0.5)) / VIEW_W) * 100}%`,
                transform: "translate(-50%, -100%)",
                background: "var(--surface)",
                border: "1px solid var(--line)",
                borderRadius: "var(--radius-sm)",
                boxShadow: "var(--shadow)",
                padding: "0.3rem 0.55rem",
                fontSize: "0.78rem",
                whiteSpace: "nowrap",
                pointerEvents: "none",
              }}
            >
              <strong>
                {weeks[active].quantity} {unit}
              </strong>{" "}
              <span style={{ color: "var(--muted)" }}>week of {weekLabel(weeks[active].week)}</span>
            </div>
          )}
        </div>
      )}
      <details>
        <summary style={{ cursor: "pointer", color: "var(--muted)", fontSize: "0.8rem" }}>Show numbers</summary>
        <table style={{ ...styles.table, fontSize: "0.82rem", marginTop: "0.35rem" }}>
          <thead>
            <tr>
              <th style={styles.th}>Week of</th>
              <th style={{ ...styles.th, textAlign: "right" }}>{unit}</th>
            </tr>
          </thead>
          <tbody>
            {weeks.map((row) => (
              <tr key={row.week}>
                <td style={styles.td}>{weekLabel(row.week)}</td>
                <td style={{ ...styles.td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{row.quantity}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
