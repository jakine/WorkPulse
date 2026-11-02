import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ProgressMeter, StatusBadge, WeeklyColumns } from "./charts";
import { ErrorText, formatDay, styles } from "./ui";

function ScopeProgress({ scope }) {
  const unit = scope.measure_symbol;
  return (
    <section style={{ display: "grid", gap: "0.6rem", paddingTop: "1rem", borderTop: "1px solid var(--line)" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem 1rem", alignItems: "center", justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>{scope.work_type_name}</h3>
        <StatusBadge status={scope.status} />
      </div>
      <ProgressMeter percent={scope.percent} status={scope.status} label={`${scope.work_type_name}: ${scope.percent}% done`} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem 1.5rem", fontSize: "0.9rem" }}>
        <span>
          <strong>{scope.percent}%</strong> · {scope.done} of {scope.planned} {unit}
        </span>
        <span>
          Pace {scope.recent_daily_rate} {unit} a day
        </span>
        {scope.per_worker_day && (
          <span>
            {scope.per_worker_day} {unit} per worker-day
          </span>
        )}
        <span>
          Forecast {scope.forecast_finish ? formatDay(scope.forecast_finish) : "—"}
          {scope.planned_finish ? ` · planned ${formatDay(scope.planned_finish)}` : ""}
        </span>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(16rem, 1fr))",
          gap: "1rem 2rem",
          alignItems: "start",
        }}
      >
        <WeeklyColumns title={`${scope.work_type_name} per week (${unit})`} unit={unit} weeks={scope.weekly} />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.35rem" }}>By team</div>
          {scope.by_team.length === 0 ? (
            <p style={{ margin: 0, color: "var(--muted)", fontSize: "0.85rem" }}>No reports yet.</p>
          ) : (
            <table style={{ ...styles.table, fontSize: "0.85rem" }}>
              <thead>
                <tr>
                  <th style={styles.th}>Team</th>
                  <th style={{ ...styles.th, textAlign: "right" }}>Done</th>
                  <th style={{ ...styles.th, textAlign: "right" }}>Share</th>
                  <th style={{ ...styles.th, textAlign: "right" }}>Per worker-day</th>
                </tr>
              </thead>
              <tbody>
                {scope.by_team.map((row) => (
                  <tr key={row.team}>
                    <td style={styles.td}>
                      {row.team_number} · {row.team_name}
                    </td>
                    <td style={{ ...styles.td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {row.quantity} {unit}
                    </td>
                    <td style={{ ...styles.td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{row.share_percent}%</td>
                    <td style={{ ...styles.td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {row.per_worker_day ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </section>
  );
}

function ProjectProgress({ projectId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api(`/projects/${projectId}/progress/`)
      .then(setData)
      .catch((err) => setError(err.message));
  }, [projectId]);

  if (error) return <ErrorText>{error}</ErrorText>;
  if (!data || data.scopes.length === 0) return null;

  return (
    <div style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Progress by work type</h2>
      <p style={{ margin: "0 0 0.25rem", color: "var(--muted)" }}>
        Pace is the average over the last {data.recent_working_days} working days up to {formatDay(data.as_of)}. The
        forecast assumes that pace continues. Output per worker-day counts days where the crew was recorded.
      </p>
      <div style={{ display: "grid", gap: "1.25rem" }}>
        {data.scopes.map((scope) => (
          <ScopeProgress key={scope.scope} scope={scope} />
        ))}
      </div>
    </div>
  );
}

export default ProjectProgress;
