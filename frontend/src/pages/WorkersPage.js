import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiList } from "../api/client";
import { ErrorText, Field, styles } from "../components/ui";
import { useRole } from "../context/AuthContext";

const emptyForm = {
  name: "",
  contact: "",
  status: "active",
  worker_type: "",
  team: "",
};

function WorkersPage() {
  const { canManage } = useRole();
  const [workers, setWorkers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [workerTypes, setWorkerTypes] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [typeName, setTypeName] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const [people, teamRows, typeRows] = await Promise.all([
      apiList("/workers/"),
      apiList("/teams/"),
      apiList("/worker-types/"),
    ]);
    setWorkers(people);
    setTeams(teamRows);
    setWorkerTypes(typeRows);
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function createWorker(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/workers/", {
        method: "POST",
        body: {
          name: form.name,
          contact: form.contact,
          status: form.status,
          worker_type: form.worker_type ? Number(form.worker_type) : null,
          team: form.team ? Number(form.team) : null,
        },
      });
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={styles.page}>
      <h1 style={{ margin: 0 }}>Workers</h1>
      <p style={{ margin: 0 }}>
        A worker belongs to one team at a time. Open a worker to move them and see their team history.
      </p>
      <ErrorText>{error}</ErrorText>

      {canManage && (
      <>
      <form
        style={styles.card}
        onSubmit={async (event) => {
          event.preventDefault();
          setError("");
          try {
            await api("/worker-types/", { method: "POST", body: { name: typeName } });
            setTypeName("");
            await load();
          } catch (err) {
            setError(err.message);
          }
        }}
      >
        <h2 style={{ marginTop: 0 }}>Worker types</h2>
        <div style={styles.row}>
          <Field label="Name">
            <input style={styles.input} value={typeName} onChange={(e) => setTypeName(e.target.value)} required />
          </Field>
          <button style={styles.button} type="submit">
            Add type
          </button>
        </div>
        {workerTypes.length > 0 && <p>{workerTypes.map((type) => type.name).join(", ")}</p>}
      </form>

      <form onSubmit={createWorker} style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Add worker</h2>
        <div style={styles.row}>
          <Field label="Name">
            <input style={styles.input} value={form.name} onChange={(e) => setField("name", e.target.value)} required />
          </Field>
          <Field label="Contact">
            <input style={styles.input} value={form.contact} onChange={(e) => setField("contact", e.target.value)} />
          </Field>
          <Field label="Type">
            <select style={styles.input} value={form.worker_type} onChange={(e) => setField("worker_type", e.target.value)}>
              <option value="">None</option>
              {workerTypes.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Status">
            <select style={styles.input} value={form.status} onChange={(e) => setField("status", e.target.value)}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </Field>
          <Field label="Team">
            <select style={styles.input} value={form.team} onChange={(e) => setField("team", e.target.value)}>
              <option value="">None</option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.number} · {team.name}
                </option>
              ))}
            </select>
          </Field>
          <button style={styles.button} type="submit">
            Add
          </button>
        </div>
      </form>
      </>
      )}

      <div style={styles.card}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Name</th>
              <th style={styles.th}>Type</th>
              <th style={styles.th}>Team</th>
              <th style={styles.th}>Status</th>
            </tr>
          </thead>
          <tbody>
            {workers.map((worker) => (
              <tr key={worker.id}>
                <td style={styles.td}>
                  <Link to={`/workers/${worker.id}`}>{worker.name}</Link>
                </td>
                <td style={styles.td}>{worker.worker_type_name || "—"}</td>
                <td style={styles.td}>
                  {worker.team ? <Link to={`/teams/${worker.team}`}>{worker.team_number} · {worker.team_name}</Link> : "—"}
                </td>
                <td style={styles.td}>{worker.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default WorkersPage;
