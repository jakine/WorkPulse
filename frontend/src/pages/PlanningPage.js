import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiList } from "../api/client";
import { addDays, isoDate, parseDate, startOfWeek } from "../components/ReportCalendar";
import { ErrorText, Field, PageHeader, companyToday, formatDay, styles } from "../components/ui";
import { useAuth, useRole } from "../context/AuthContext";

function projectColor(projectId) {
  // Color follows the project (by id), never its position in the list.
  const slot = `var(--cat-${((projectId - 1) % 8) + 1})`;
  return { fill: `color-mix(in srgb, ${slot} 26%, var(--surface))`, edge: slot };
}

function covers(row, day) {
  return row.start_date <= day && (!row.end_date || row.end_date >= day);
}

const teamColumn = {
  position: "sticky",
  left: 0,
  zIndex: 3,
  background: "var(--surface)",
  borderRight: "1px solid var(--line)",
  borderBottom: "1px solid var(--line)",
  padding: "0.45rem 0.7rem",
  textAlign: "left",
  minWidth: "11rem",
  fontWeight: 600,
};
const dayHead = {
  borderBottom: "1px solid var(--line)",
  padding: "0.35rem 0",
  width: "2.2rem",
  minWidth: "2.2rem",
  textAlign: "center",
  fontSize: "0.72rem",
  fontWeight: 500,
};
const barBase = {
  display: "block",
  width: "100%",
  flex: 1,
  minHeight: "0.8rem",
  border: "none",
  padding: 0,
};

const emptyForm = { team: "", workplace: "", start_date: "", end_date: "" };

function PlanningPage() {
  const { user } = useAuth();
  const { canManage } = useRole();
  const today = companyToday(user?.active_company);
  const [start, setStart] = useState(() => isoDate(startOfWeek(parseDate(today))));
  const [weeks, setWeeks] = useState(3);
  const [teams, setTeams] = useState([]);
  const [projects, setProjects] = useState([]);
  const [placements, setPlacements] = useState([]);
  const [form, setForm] = useState({ ...emptyForm, start_date: today });
  const [editing, setEditing] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [error, setError] = useState("");

  const days = useMemo(
    () => Array.from({ length: weeks * 7 }, (_, index) => isoDate(addDays(parseDate(start), index))),
    [start, weeks]
  );
  const end = days[days.length - 1];

  const load = useCallback(async () => {
    const [teamRows, projectRows, placementRows] = await Promise.all([
      apiList("/teams/"),
      apiList("/projects/"),
      apiList(`/workplace-teams/?active_from=${start}&active_to=${end}`),
    ]);
    setTeams(teamRows);
    setProjects(projectRows);
    setPlacements(placementRows);
  }, [start, end]);

  useEffect(() => {
    setError("");
    load().catch((err) => setError(err.message));
  }, [load]);

  const colors = useMemo(() => new Map(projects.map((project) => [project.id, projectColor(project.id)])), [projects]);
  const openProjects = projects.filter((project) => project.status !== "completed");

  function shift(daysToMove) {
    setStart((current) => isoDate(addDays(parseDate(current), daysToMove)));
  }

  async function run(action) {
    setError("");
    setWarnings([]);
    try {
      const result = await action();
      setWarnings(result?.warnings || []);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  function place(event) {
    event.preventDefault();
    run(async () => {
      const result = await api("/workplace-teams/", {
        method: "POST",
        body: {
          team: Number(form.team),
          workplace: Number(form.workplace),
          start_date: form.start_date,
          end_date: form.end_date || null,
        },
      });
      setForm({ ...emptyForm, start_date: form.start_date });
      return result;
    });
  }

  function saveEditing(event) {
    event.preventDefault();
    run(async () => {
      const result = await api(`/workplace-teams/${editing.id}/`, {
        method: "PATCH",
        body: { start_date: editing.start_date, end_date: editing.end_date || null },
      });
      setEditing(null);
      return result;
    });
  }

  function removeEditing() {
    if (!window.confirm(`Take ${editing.team_name} off ${editing.workplace_name}?`)) return;
    run(async () => {
      await api(`/workplace-teams/${editing.id}/`, { method: "DELETE" });
      setEditing(null);
    });
  }

  function renderBar(row, day, index, count) {
    const color = colors.get(row.workplace) || projectColor(row.workplace);
    const runStart = day === row.start_date || day === days[0];
    const title = `${row.workplace_name}: ${formatDay(row.start_date)} – ${row.end_date ? formatDay(row.end_date) : "no end date"}`;
    const style = {
      ...barBase,
      background: color.fill,
      borderTop: `2px solid ${color.edge}`,
      cursor: canManage ? "pointer" : "default",
      outline: editing?.id === row.id ? "2px solid var(--ink)" : "none",
    };
    const label = runStart ? (
      <span
        style={{
          position: "absolute",
          left: "0.25rem",
          top: `calc(${(index * 100) / count}% + 0.1rem)`,
          zIndex: 2,
          whiteSpace: "nowrap",
          fontSize: "0.7rem",
          fontWeight: 650,
          color: "var(--ink)",
          pointerEvents: "none",
        }}
      >
        {row.workplace_name}
      </span>
    ) : null;
    return (
      <span key={row.id} style={{ display: "contents" }}>
        {label}
        {canManage ? (
          <button type="button" style={style} title={title} onClick={() => setEditing({ ...row, end_date: row.end_date || "" })} />
        ) : (
          <span style={style} title={title} />
        )}
      </span>
    );
  }

  return (
    <div style={styles.page}>
      <PageHeader title="Planning">Which team works where, day by day.</PageHeader>
      <ErrorText>{error}</ErrorText>

      <div style={{ ...styles.row, alignItems: "center" }}>
        <button type="button" style={styles.quiet} onClick={() => shift(-7)}>
          ← Earlier
        </button>
        <button type="button" style={styles.quiet} onClick={() => setStart(isoDate(startOfWeek(parseDate(today))))}>
          This week
        </button>
        <button type="button" style={styles.quiet} onClick={() => shift(7)}>
          Later →
        </button>
        <select style={styles.input} value={weeks} onChange={(e) => setWeeks(Number(e.target.value))} aria-label="Weeks shown">
          <option value={2}>2 weeks</option>
          <option value={3}>3 weeks</option>
          <option value={4}>4 weeks</option>
        </select>
        <strong>
          {formatDay(start)} – {formatDay(end)}
        </strong>
      </div>

      <div style={{ overflowX: "auto", border: "1px solid var(--line)", borderRadius: "var(--radius)", background: "var(--surface)" }}>
        <table style={{ borderCollapse: "separate", borderSpacing: 0, fontSize: "0.82rem" }}>
          <thead>
            <tr>
              <th style={{ ...teamColumn, color: "var(--muted)", fontSize: "0.75rem" }}>Team</th>
              {days.map((day) => {
                const date = parseDate(day);
                const weekend = date.getDay() === 0 || date.getDay() === 6;
                return (
                  <th
                    key={day}
                    style={{
                      ...dayHead,
                      background: weekend ? "var(--surface-2)" : "transparent",
                      color: day === today ? "var(--accent)" : "var(--muted)",
                      borderLeft: date.getDay() === 1 ? "1px solid var(--line)" : "none",
                    }}
                  >
                    <div>{date.toLocaleDateString(undefined, { weekday: "narrow" })}</div>
                    <div style={{ fontWeight: day === today ? 750 : 600 }}>{date.getDate()}</div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {teams.map((team) => (
              <tr key={team.id}>
                <th scope="row" style={teamColumn}>
                  <Link to={`/teams/${team.id}`}>
                    {team.number} · {team.name}
                  </Link>
                  <div style={{ color: "var(--muted)", fontSize: "0.72rem", fontWeight: 400 }}>
                    {team.member_count || team.worker_count} workers
                  </div>
                </th>
                {days.map((day) => {
                  const date = parseDate(day);
                  const weekend = date.getDay() === 0 || date.getDay() === 6;
                  const here = placements.filter((row) => row.team === team.id && covers(row, day));
                  const clash = here.length > 1;
                  return (
                    <td
                      key={day}
                      title={clash ? `Booked on ${here.length} projects: ${here.map((row) => row.workplace_name).join(", ")}` : undefined}
                      style={{
                        position: "relative",
                        height: "2.6rem",
                        padding: 0,
                        borderBottom: "1px solid var(--line)",
                        borderLeft: date.getDay() === 1 ? "1px solid var(--line)" : "none",
                        background: weekend ? "var(--surface-2)" : "transparent",
                        boxShadow: clash ? "inset 0 0 0 2px var(--danger)" : "none",
                      }}
                    >
                      <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
                        {here.map((row, index) => renderBar(row, day, index, here.length))}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {teams.length === 0 && <p style={{ padding: "1rem" }}>Add teams first, then place them on projects here.</p>}
      </div>

      {warnings.length > 0 && (
        <div style={{ ...styles.card, borderColor: "var(--warn)" }} role="status">
          <strong style={{ color: "var(--warn)" }}>Saved, but this team is double-booked</strong>
          <ul style={{ margin: "0.4rem 0 0" }}>
            {warnings.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </div>
      )}

      {canManage && editing && (
        <form onSubmit={saveEditing} style={styles.card}>
          <h2 style={{ marginTop: 0 }}>
            {editing.team_number} · {editing.team_name} on {editing.workplace_name}
          </h2>
          <div style={styles.row}>
            <Field label="From">
              <input
                style={styles.input}
                type="date"
                value={editing.start_date}
                onChange={(e) => setEditing({ ...editing, start_date: e.target.value })}
                required
              />
            </Field>
            <Field label="To">
              <input
                style={styles.input}
                type="date"
                min={editing.start_date}
                value={editing.end_date}
                onChange={(e) => setEditing({ ...editing, end_date: e.target.value })}
              />
            </Field>
            <button style={styles.button} type="submit">
              Save
            </button>
            <button style={styles.danger} type="button" onClick={removeEditing}>
              Take off project
            </button>
            <button style={styles.quiet} type="button" onClick={() => setEditing(null)}>
              Close
            </button>
          </div>
        </form>
      )}

      {canManage && (
        <form onSubmit={place} style={styles.card}>
          <h2 style={{ marginTop: 0 }}>Place a team</h2>
          <div style={styles.row}>
            <Field label="Team">
              <select style={styles.input} value={form.team} onChange={(e) => setForm({ ...form, team: e.target.value })} required>
                <option value="">Choose</option>
                {teams.map((team) => (
                  <option key={team.id} value={team.id}>
                    {team.number} · {team.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Project">
              <select
                style={styles.input}
                value={form.workplace}
                onChange={(e) => setForm({ ...form, workplace: e.target.value })}
                required
              >
                <option value="">Choose</option>
                {openProjects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="From">
              <input
                style={styles.input}
                type="date"
                value={form.start_date}
                onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                required
              />
            </Field>
            <Field label="To (optional)">
              <input
                style={styles.input}
                type="date"
                min={form.start_date}
                value={form.end_date}
                onChange={(e) => setForm({ ...form, end_date: e.target.value })}
              />
            </Field>
            <button style={styles.button} type="submit">
              Place team
            </button>
          </div>
        </form>
      )}

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Projects in this period</h2>
        {openProjects.length === 0 ? (
          <p>No open projects.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "0.5rem" }}>
            {openProjects.map((project) => {
              const color = colors.get(project.id);
              const placed = new Set(placements.filter((row) => row.workplace === project.id).map((row) => row.team)).size;
              const short = project.teams_needed != null && placed < project.teams_needed;
              return (
                <li key={project.id} style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
                  <span
                    aria-hidden="true"
                    style={{ width: "0.9rem", height: "0.9rem", borderRadius: "3px", background: color.fill, border: `2px solid ${color.edge}` }}
                  />
                  <Link to={`/projects/${project.id}`}>{project.name}</Link>
                  <span style={{ color: short ? "var(--warn)" : "var(--muted)" }}>
                    {project.teams_needed != null
                      ? `${placed} of ${project.teams_needed} teams placed`
                      : `${placed} ${placed === 1 ? "team" : "teams"} placed`}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}

export default PlanningPage;
