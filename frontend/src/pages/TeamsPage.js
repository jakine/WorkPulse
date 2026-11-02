import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiList } from "../api/client";
import { ErrorText, Field, styles } from "../components/ui";
import { useRole } from "../context/AuthContext";

const emptyForm = { number: "", name: "", worker_count: "", lead_note: "", lead_user: "" };

function TeamsPage() {
  const { canManage } = useRole();
  const [teams, setTeams] = useState([]);
  const [members, setMembers] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    const [teamRows, memberRows] = await Promise.all([apiList("/teams/"), apiList("/companies/members/")]);
    setTeams(teamRows);
    setMembers(memberRows);
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function editTeam(team) {
    setEditingId(team.id);
    setForm({
      number: String(team.number),
      name: team.name,
      worker_count: String(team.worker_count),
      lead_note: team.lead_note || "",
      lead_user: team.lead_user ? String(team.lead_user) : "",
    });
  }

  async function saveTeam(event) {
    event.preventDefault();
    setError("");
    const body = {
      number: Number(form.number),
      name: form.name,
      worker_count: Number(form.worker_count),
      lead_note: form.lead_note,
      lead_user: form.lead_user ? Number(form.lead_user) : null,
    };
    try {
      if (editingId) {
        await api(`/teams/${editingId}/`, { method: "PATCH", body });
      } else {
        await api("/teams/", { method: "POST", body });
      }
      setForm(emptyForm);
      setEditingId(null);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={styles.page}>
      <h1 style={{ margin: 0 }}>Teams</h1>
      <p style={{ margin: 0 }}>
        Each team has a number, a worker count, and a note for its team leads. You can also link a company user as the lead.
      </p>
      <ErrorText>{error}</ErrorText>

      {canManage && (
      <form onSubmit={saveTeam} style={styles.card}>
        <h2 style={{ marginTop: 0 }}>{editingId ? "Edit team" : "Add team"}</h2>
        <div style={styles.row}>
          <Field label="Team number">
            <input
              style={styles.input}
              type="number"
              min="1"
              step="1"
              value={form.number}
              onChange={(e) => setField("number", e.target.value)}
              required
            />
          </Field>
          <Field label="Name">
            <input style={styles.input} value={form.name} onChange={(e) => setField("name", e.target.value)} required />
          </Field>
          <Field label="Crew size (planned)">
            <input
              style={styles.input}
              type="number"
              min="0"
              step="1"
              value={form.worker_count}
              onChange={(e) => setField("worker_count", e.target.value)}
              required
            />
          </Field>
          <Field label="Team leads (note)">
            <input
              style={styles.input}
              value={form.lead_note}
              onChange={(e) => setField("lead_note", e.target.value)}
              placeholder="Names of the leads"
            />
          </Field>
          <Field label="Linked user">
            <select style={styles.input} value={form.lead_user} onChange={(e) => setField("lead_user", e.target.value)}>
              <option value="">None</option>
              {members.map((member) => (
                <option key={member.id} value={member.user}>
                  {member.email}
                </option>
              ))}
            </select>
          </Field>
          <button style={styles.button} type="submit">
            {editingId ? "Save" : "Add team"}
          </button>
          {editingId && (
            <button
              style={styles.button}
              type="button"
              onClick={() => {
                setEditingId(null);
                setForm(emptyForm);
              }}
            >
              Cancel
            </button>
          )}
        </div>
      </form>
      )}

      <div style={styles.card}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Number</th>
              <th style={styles.th}>Name</th>
              <th style={styles.th}>Members</th>
              <th style={styles.th}>Crew size</th>
              <th style={styles.th}>Team leads</th>
              <th style={styles.th}>Linked user</th>
              <th style={styles.th}></th>
            </tr>
          </thead>
          <tbody>
            {teams.map((team) => (
              <tr key={team.id}>
                <td style={styles.td}>{team.number}</td>
                <td style={styles.td}>
                  <Link to={`/teams/${team.id}`}>{team.name}</Link>
                </td>
                <td style={styles.td}>{team.member_count}</td>
                <td style={styles.td}>{team.worker_count}</td>
                <td style={styles.td}>{team.lead_note || "—"}</td>
                <td style={styles.td}>{team.lead_user_email || "—"}</td>
                <td style={styles.td}>
                  {canManage && (
                    <button type="button" style={styles.button} onClick={() => editTeam(team)}>
                      Edit
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {teams.length === 0 && <p>No teams yet.</p>}
      </div>
    </div>
  );
}

export default TeamsPage;
