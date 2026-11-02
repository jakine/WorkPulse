import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { WeeklyColumns } from "../components/charts";
import { addDays, isoDate, parseDate, startOfWeek } from "../components/ReportCalendar";
import { Badge, ErrorText, PageHeader, companyToday, formatDay, styles } from "../components/ui";
import { useAuth } from "../context/AuthContext";

function placementState(row, today) {
  if (row.start_date > today) return ["Upcoming", "var(--muted)"];
  if (row.end_date && row.end_date < today) return ["Ended", "var(--faint)"];
  return ["On site now", "var(--accent)"];
}

const PERIODS = [
  [4, "Last 4 weeks"],
  [8, "Last 8 weeks"],
  [12, "Last 12 weeks"],
];

function TeamOutput({ teamId, today }) {
  const [weeks, setWeeks] = useState(8);
  const [performance, setPerformance] = useState(null);
  const [error, setError] = useState("");
  const start = isoDate(addDays(startOfWeek(parseDate(today)), -7 * (weeks - 1)));

  useEffect(() => {
    setError("");
    api(`/teams/${teamId}/performance/?from=${start}&to=${today}`)
      .then(setPerformance)
      .catch((err) => (err.status === 403 ? setPerformance(null) : setError(err.message)));
  }, [teamId, start, today]);

  if (error) return <ErrorText>{error}</ErrorText>;
  if (!performance) return null;

  return (
    <div style={styles.card}>
      <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap", justifyContent: "space-between" }}>
        <h2 style={{ margin: 0 }}>Output</h2>
        <select style={styles.input} value={weeks} onChange={(e) => setWeeks(Number(e.target.value))} aria-label="Period">
          {PERIODS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <p style={{ color: "var(--muted)" }}>
        {formatDay(performance.from)} – {formatDay(performance.to)} · {performance.days_reported} days with reports ·{" "}
        {performance.crew_days} crew days recorded
      </p>
      {performance.work_types.length === 0 ? (
        <p style={{ margin: 0 }}>No reports in this period.</p>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(17rem, 1fr))", gap: "1.25rem 2rem" }}>
          {performance.work_types.map((row) => (
            <div key={row.work_type} style={{ display: "grid", gap: "0.4rem", minWidth: 0, alignContent: "start" }}>
              <WeeklyColumns title={`${row.name} (${row.measure_symbol})`} unit={row.measure_symbol} weeks={row.weekly} />
              <div style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
                {row.quantity} {row.measure_symbol} in total · {row.per_team_day ?? "—"} per team-day ·{" "}
                {row.per_worker_day ?? "—"} per worker-day
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TeamPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const today = companyToday(user?.active_company);
  const [team, setTeam] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api(`/teams/${id}/`)
      .then(setTeam)
      .catch((err) => setError(err.message));
  }, [id]);

  const onSiteNow = (team?.placements || []).filter((row) => placementState(row, today)[0] === "On site now");
  const lead = team ? [team.lead_user_email, team.lead_note].filter(Boolean).join(" · ") : "";

  return (
    <div style={styles.page}>
      <Link to="/teams">← Teams</Link>
      <PageHeader title={team ? `${team.number} · ${team.name}` : "Team"}>{lead ? `Lead: ${lead}` : null}</PageHeader>
      <ErrorText>{error}</ErrorText>
      {team && (
        <>
          <div style={styles.stats}>
            <div style={styles.stat}>
              <div style={styles.label}>Registered members</div>
              <strong>{team.member_count}</strong>
            </div>
            <div style={styles.stat}>
              <div style={styles.label}>Crew size (planned)</div>
              <strong>{team.worker_count}</strong>
            </div>
            <div style={styles.stat}>
              <div style={styles.label}>Projects today</div>
              <strong>{onSiteNow.length}</strong>
            </div>
          </div>

          <TeamOutput teamId={team.id} today={today} />

          <div style={styles.card}>
            <h2 style={{ marginTop: 0 }}>Members</h2>
            {team.members.length === 0 ? (
              <p>No workers in this team right now.</p>
            ) : (
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Name</th>
                    <th style={styles.th}>Type</th>
                    <th style={styles.th}>In team since</th>
                  </tr>
                </thead>
                <tbody>
                  {team.members.map((row) => (
                    <tr key={row.id}>
                      <td style={styles.td}>
                        <Link to={`/workers/${row.worker}`}>{row.worker_name}</Link>
                      </td>
                      <td style={styles.td}>{row.worker_type_name || "—"}</td>
                      <td style={styles.td}>{row.start_date ? formatDay(row.start_date) : "Before records"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div style={styles.card}>
            <h2 style={{ marginTop: 0 }}>Projects</h2>
            {team.placements.length === 0 ? (
              <p>This team has not been placed on a project.</p>
            ) : (
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Project</th>
                    <th style={styles.th}>From</th>
                    <th style={styles.th}>To</th>
                    <th style={styles.th}></th>
                  </tr>
                </thead>
                <tbody>
                  {team.placements.map((row) => {
                    const [label, color] = placementState(row, today);
                    return (
                      <tr key={row.id}>
                        <td style={styles.td}>
                          <Link to={`/projects/${row.workplace}`}>{row.workplace_name}</Link>
                        </td>
                        <td style={styles.td}>{formatDay(row.start_date)}</td>
                        <td style={styles.td}>{row.end_date ? formatDay(row.end_date) : "No end date"}</td>
                        <td style={styles.td}>
                          <Badge color={color}>{label}</Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {team.past_members.length > 0 && (
            <div style={styles.card}>
              <h2 style={{ marginTop: 0 }}>Past members</h2>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Name</th>
                    <th style={styles.th}>From</th>
                    <th style={styles.th}>To</th>
                  </tr>
                </thead>
                <tbody>
                  {team.past_members.map((row) => (
                    <tr key={row.id}>
                      <td style={styles.td}>
                        <Link to={`/workers/${row.worker}`}>{row.worker_name}</Link>
                      </td>
                      <td style={styles.td}>{row.start_date ? formatDay(row.start_date) : "Before records"}</td>
                      <td style={styles.td}>{formatDay(row.end_date)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default TeamPage;
