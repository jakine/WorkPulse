import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, apiList } from "../api/client";
import { ErrorText, Field, PageHeader, companyToday, formatDay, styles } from "../components/ui";
import { useAuth, useRole } from "../context/AuthContext";

function WorkerPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const { canManage } = useRole();
  const today = companyToday(user?.active_company);
  const [worker, setWorker] = useState(null);
  const [teams, setTeams] = useState([]);
  const [move, setMove] = useState({ team: "", on_date: today });
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [detail, teamRows] = await Promise.all([api(`/workers/${id}/`), apiList("/teams/")]);
    setWorker(detail);
    setTeams(teamRows);
  }, [id]);

  useEffect(() => {
    setError("");
    load().catch((err) => setError(err.message));
  }, [load]);

  async function submitMove(event) {
    event.preventDefault();
    setError("");
    try {
      const detail = await api(`/workers/${id}/move/`, {
        method: "POST",
        body: { team: move.team === "none" ? null : Number(move.team), on_date: move.on_date },
      });
      setWorker(detail);
      setMove({ team: "", on_date: today });
    } catch (err) {
      setError(err.message);
    }
  }

  const current = (worker?.memberships || []).find((row) => !row.end_date);
  const details = worker
    ? [worker.worker_type_name, worker.status === "active" ? "Active" : "Inactive", worker.contact].filter(Boolean).join(" · ")
    : null;

  return (
    <div style={styles.page}>
      <Link to="/workers">← Workers</Link>
      <PageHeader title={worker?.name || "Worker"}>{details}</PageHeader>
      <ErrorText>{error}</ErrorText>
      {worker && (
        <>
          <div style={styles.stats}>
            <div style={styles.stat}>
              <div style={styles.label}>Current team</div>
              <strong>
                {worker.team ? (
                  <Link to={`/teams/${worker.team}`}>
                    {worker.team_number} · {worker.team_name}
                  </Link>
                ) : (
                  "No team"
                )}
              </strong>
            </div>
            <div style={styles.stat}>
              <div style={styles.label}>In this team since</div>
              <strong>{current ? (current.start_date ? formatDay(current.start_date) : "Before records") : "—"}</strong>
            </div>
          </div>

          {canManage && (
            <form onSubmit={submitMove} style={styles.card}>
              <h2 style={{ marginTop: 0 }}>Move to another team</h2>
              <p style={{ marginTop: 0 }}>
                The current team ends the day before the move. You can record a move that already happened.
              </p>
              <div style={styles.row}>
                <Field label="New team">
                  <select
                    style={styles.input}
                    value={move.team}
                    onChange={(e) => setMove({ ...move, team: e.target.value })}
                    required
                  >
                    <option value="" disabled>
                      Choose
                    </option>
                    {teams
                      .filter((team) => team.id !== worker.team)
                      .map((team) => (
                        <option key={team.id} value={team.id}>
                          {team.number} · {team.name}
                        </option>
                      ))}
                    {worker.team && <option value="none">No team (leaves the team)</option>}
                  </select>
                </Field>
                <Field label="From">
                  <input
                    style={styles.input}
                    type="date"
                    max={today}
                    value={move.on_date}
                    onChange={(e) => setMove({ ...move, on_date: e.target.value })}
                    required
                  />
                </Field>
                <button style={styles.button} type="submit">
                  Move
                </button>
              </div>
            </form>
          )}

          <div style={styles.card}>
            <h2 style={{ marginTop: 0 }}>Team history</h2>
            {worker.memberships.length === 0 ? (
              <p>No team yet.</p>
            ) : (
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Team</th>
                    <th style={styles.th}>From</th>
                    <th style={styles.th}>To</th>
                  </tr>
                </thead>
                <tbody>
                  {worker.memberships.map((row) => (
                    <tr key={row.id}>
                      <td style={styles.td}>
                        <Link to={`/teams/${row.team}`}>
                          {row.team_number} · {row.team_name}
                        </Link>
                      </td>
                      <td style={styles.td}>{row.start_date ? formatDay(row.start_date) : "Before records"}</td>
                      <td style={styles.td}>{row.end_date ? formatDay(row.end_date) : "Now"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default WorkerPage;
