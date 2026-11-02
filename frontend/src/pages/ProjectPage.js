import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, apiList } from "../api/client";
import ActivityList from "../components/ActivityList";
import DailyReports from "../components/DailyReports";
import ProjectProgress from "../components/ProjectProgress";
import SiteMaterials from "../components/SiteMaterials";
import TaskBoard from "../components/TaskBoard";
import TaskTimeline from "../components/TaskTimeline";
import WorkSheet from "../components/WorkSheet";
import { ErrorText, Field, Tabs, styles } from "../components/ui";
import { useRole } from "../context/AuthContext";

const TABS = [
  ["overview", "Overview"],
  ["board", "Board"],
  ["sheet", "Sheet"],
  ["timeline", "Timeline"],
  ["teams", "Teams"],
  ["reports", "Daily log"],
  ["stock", "Stock"],
];

const crewTable = {
  width: "100%",
  borderCollapse: "separate",
  borderSpacing: "0 0.75rem",
};
const crewHead = { ...styles.th, borderBottom: "none", padding: "0.35rem 1rem" };
const crewCell = {
  padding: "1rem",
  background: "var(--surface-2)",
  verticalAlign: "top",
};

function lengthLabel(place) {
  if (!place.length_count || !place.length_unit) return "No length set";
  const unit = place.length_unit_name || "";
  const days = place.length_days != null ? ` (${place.length_days} days)` : "";
  return `${place.length_count} ${unit}${days}`;
}

function Overview({ place, onChange }) {
  const { canManage } = useRole();
  const [events, setEvents] = useState([]);
  const [workTypes, setWorkTypes] = useState([]);
  const [durationUnits, setDurationUnits] = useState([]);
  const [scopeForm, setScopeForm] = useState({
    work_type: "",
    planned_quantity: "",
    length_count: "",
    length_unit: "",
    teams_needed: "",
  });
  const [error, setError] = useState("");

  useEffect(() => {
    apiList(`/activity/?project=${place.id}`)
      .then(setEvents)
      .catch((err) => setError(err.message));
  }, [place.id]);

  useEffect(() => {
    if (!canManage) return;
    Promise.all([apiList("/work-types/"), apiList("/duration-units/")])
      .then(([typeRows, unitRows]) => {
        setWorkTypes(typeRows);
        setDurationUnits(unitRows);
      })
      .catch((err) => setError(err.message));
  }, [canManage]);

  async function addScope(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/project-scopes/", {
        method: "POST",
        body: {
          workplace: place.id,
          work_type: Number(scopeForm.work_type),
          planned_quantity: scopeForm.planned_quantity,
          length_count: scopeForm.length_count ? Number(scopeForm.length_count) : null,
          length_unit: scopeForm.length_unit ? Number(scopeForm.length_unit) : null,
          teams_needed: scopeForm.teams_needed ? Number(scopeForm.teams_needed) : null,
          position: (place.scopes || []).length,
        },
      });
      setScopeForm({ work_type: "", planned_quantity: "", length_count: "", length_unit: "", teams_needed: "" });
      await onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeScope(scopeId) {
    if (!window.confirm("Delete this planned work line?")) return;
    setError("");
    try {
      await api(`/project-scopes/${scopeId}/`, { method: "DELETE" });
      await onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  const symbol = place.measure_symbol ? ` ${place.measure_symbol}` : "";
  const usedTypes = new Set((place.scopes || []).map((scope) => scope.work_type));
  return (
    <>
      <div style={styles.stats}>
        <div style={styles.stat}>
          <div style={styles.label}>Progress</div>
          <strong>{place.progress_percent != null ? `${place.progress_percent}%` : "—"}</strong>
        </div>
        <div style={styles.stat}>
          <div style={styles.label}>Done</div>
          <strong>
            {place.done_quantity != null ? `${place.done_quantity}${symbol}` : "—"}
          </strong>
        </div>
        <div style={styles.stat}>
          <div style={styles.label}>Remaining</div>
          <strong>{place.remaining_quantity != null ? `${place.remaining_quantity}${symbol}` : "—"}</strong>
        </div>
        <div style={styles.stat}>
          <div style={styles.label}>Days</div>
          <strong>
            {place.days_worked}
            {place.length_days != null ? ` / ${place.length_days}` : ""}
            {place.remaining_days != null ? ` · ${place.remaining_days} left` : ""}
          </strong>
        </div>
        <div style={styles.stat}>
          <div style={styles.label}>Teams</div>
          <strong>
            {(place.teams || []).length}
            {place.teams_needed != null ? ` / ${place.teams_needed} needed` : ""}
          </strong>
        </div>
      </div>
      <ProjectProgress projectId={place.id} />
      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Work scopes</h2>
        <p style={{ marginTop: 0 }}>
          Each line is a type of work on this project. Remaining is per line so m² and m³ stay separate.
        </p>
        <ErrorText>{error}</ErrorText>
        {canManage && (
          <form onSubmit={addScope} style={{ marginBottom: "1rem" }}>
            <div style={styles.row}>
              <Field label="Type of work">
                <select
                  style={styles.input}
                  value={scopeForm.work_type}
                  onChange={(e) => setScopeForm({ ...scopeForm, work_type: e.target.value })}
                  required
                >
                  <option value="">Choose</option>
                  {workTypes
                    .filter((type) => !usedTypes.has(type.id))
                    .map((type) => (
                      <option key={type.id} value={type.id}>
                        {type.category_name} · {type.name} ({type.measure_symbol})
                      </option>
                    ))}
                </select>
              </Field>
              <Field
                label={
                  workTypes.find((type) => String(type.id) === String(scopeForm.work_type))
                    ? `Planned (${workTypes.find((type) => String(type.id) === String(scopeForm.work_type)).measure_symbol})`
                    : "Planned"
                }
              >
                <input
                  style={styles.input}
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={scopeForm.planned_quantity}
                  onChange={(e) => setScopeForm({ ...scopeForm, planned_quantity: e.target.value })}
                  required
                />
              </Field>
              <Field label="Length">
                <input
                  style={styles.input}
                  type="number"
                  min="1"
                  step="1"
                  value={scopeForm.length_count}
                  onChange={(e) => setScopeForm({ ...scopeForm, length_count: e.target.value })}
                />
              </Field>
              <Field label="Unit">
                <select
                  style={styles.input}
                  value={scopeForm.length_unit}
                  onChange={(e) => setScopeForm({ ...scopeForm, length_unit: e.target.value })}
                >
                  <option value="">None</option>
                  {durationUnits.map((unit) => (
                    <option key={unit.id} value={unit.id}>
                      {unit.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Teams needed">
                <input
                  style={styles.input}
                  type="number"
                  min="1"
                  step="1"
                  value={scopeForm.teams_needed}
                  onChange={(e) => setScopeForm({ ...scopeForm, teams_needed: e.target.value })}
                />
              </Field>
              <button style={styles.button} type="submit">
                Add scope
              </button>
            </div>
          </form>
        )}
        {(place.scopes || []).length === 0 ? (
          <p>No planned work lines yet. Add a type of work to track remaining.</p>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Work</th>
                <th style={styles.th}>Planned</th>
                <th style={styles.th}>Done</th>
                <th style={styles.th}>Remaining</th>
                <th style={styles.th}>Length</th>
                <th style={styles.th}>Teams</th>
                {canManage && <th style={styles.th}></th>}
              </tr>
            </thead>
            <tbody>
              {(place.scopes || []).map((scope) => (
                <tr key={scope.id}>
                  <td style={styles.td}>
                    {scope.work_type_category_name} · {scope.work_type_name}
                  </td>
                  <td style={styles.td}>
                    {scope.planned_quantity} {scope.measure_symbol}
                  </td>
                  <td style={styles.td}>
                    {scope.done_quantity} {scope.measure_symbol}
                  </td>
                  <td style={styles.td}>
                    {scope.remaining_quantity} {scope.measure_symbol}
                  </td>
                  <td style={styles.td}>
                    {scope.length_count && scope.length_unit_name
                      ? `${scope.length_count} ${scope.length_unit_name}${scope.length_days != null ? ` (${scope.length_days} days)` : ""}`
                      : "—"}
                  </td>
                  <td style={styles.td}>
                    {scope.teams_needed != null ? `${scope.teams_placed} / ${scope.teams_needed}` : scope.teams_placed}
                  </td>
                  {canManage && (
                    <td style={styles.td}>
                      <button type="button" style={styles.danger} onClick={() => removeScope(scope.id)}>
                        Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Recent activity</h2>
        <ActivityList events={events} />
      </div>
    </>
  );
}

function TeamsTab({ place, onChange }) {
  const { canManage } = useRole();
  const [teams, setTeams] = useState([]);
  const [teamPlacement, setTeamPlacement] = useState({ team: "", start_date: "" });
  const [warnings, setWarnings] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!canManage) return;
    apiList("/teams/")
      .then(setTeams)
      .catch((err) => setError(err.message));
  }, [canManage]);

  async function placeTeam(event) {
    event.preventDefault();
    setError("");
    setWarnings([]);
    try {
      const placed = await api("/workplace-teams/", {
        method: "POST",
        body: { workplace: place.id, team: Number(teamPlacement.team), start_date: teamPlacement.start_date },
      });
      setWarnings(placed.warnings || []);
      setTeamPlacement({ team: "", start_date: "" });
      await onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeTeam(rowId) {
    setError("");
    try {
      await api(`/workplace-teams/${rowId}/`, { method: "DELETE" });
      await onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  const placedIds = new Set((place.teams || []).map((row) => row.team));

  return (
    <div style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Teams on this project</h2>
      <ErrorText>{error}</ErrorText>
      {warnings.map((text) => (
        <p key={text} style={{ margin: 0, color: "var(--warn)" }} role="status">
          {text}
        </p>
      ))}
      {canManage && (
        <form onSubmit={placeTeam}>
          <p style={{ marginTop: 0 }}>Add one team or several. The same team can also work on other projects.</p>
          <div style={styles.row}>
            <Field label="Team">
              <select
                style={styles.input}
                value={teamPlacement.team}
                onChange={(e) => setTeamPlacement({ ...teamPlacement, team: e.target.value })}
                required
              >
                <option value="">Choose</option>
                {teams
                  .filter((team) => !placedIds.has(team.id))
                  .map((team) => (
                    <option key={team.id} value={team.id}>
                      {team.number} · {team.name}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label="From">
              <input
                style={styles.input}
                type="date"
                value={teamPlacement.start_date}
                onChange={(e) => setTeamPlacement({ ...teamPlacement, start_date: e.target.value })}
                required
              />
            </Field>
            <button style={styles.button} type="submit">
              Place team
            </button>
          </div>
        </form>
      )}
      {(place.teams || []).length === 0 ? (
        <p>No team is on this project yet.</p>
      ) : (
        <table style={crewTable}>
          <thead>
            <tr>
              <th style={crewHead}>Team</th>
              <th style={crewHead}>Workers</th>
              <th style={crewHead}>Leads</th>
              <th style={crewHead}>From</th>
              {canManage && <th style={crewHead}></th>}
            </tr>
          </thead>
          <tbody>
            {place.teams.map((row) => (
              <tr key={row.id}>
                <td style={crewCell}>
                  <strong>
                    {row.team_number} · {row.team_name}
                  </strong>
                </td>
                <td style={crewCell}>{row.worker_count}</td>
                <td style={crewCell}>{row.lead_note || row.lead_user_email || "—"}</td>
                <td style={crewCell}>{row.start_date}</td>
                {canManage && (
                  <td style={crewCell}>
                    <button type="button" style={styles.danger} onClick={() => removeTeam(row.id)}>
                      Remove
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function ReportsTab({ place, onChange }) {
  return (
    <div style={{ display: "grid", gap: "1.25rem" }}>
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <Link to={`/projects/${place.id}?tab=sheet`}>Open sheet</Link>
      </div>
      <DailyReports workplaceId={place.id} place={place} onPlaceChange={onChange} />
    </div>
  );
}

function StockTab({ place }) {
  return <SiteMaterials place={place} />;
}

function ProjectPage() {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab") || "overview";
  const tab = TABS.some(([key]) => key === requestedTab) ? requestedTab : "overview";
  const [place, setPlace] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setPlace(await api(`/projects/${id}/`));
  }, [id]);

  useEffect(() => {
    setPlace(null);
    setError("");
    load().catch((err) => setError(err.message));
  }, [id, load]);

  if (!place) return <ErrorText>{error || "Loading..."}</ErrorText>;

  return (
    <div style={styles.page}>
      <div>
        <Link to="/projects">Projects</Link>
        <h1 style={{ marginBottom: 0 }}>{place.name}</h1>
        <p style={{ marginBottom: 0 }}>
          {lengthLabel(place)}
          {place.address ? ` · ${place.address}` : ""}
          {place.work_type_name
            ? ` · ${place.work_type_category_name ? `${place.work_type_category_name} · ` : ""}${place.work_type_name}`
            : ""}
          {place.measure_symbol && place.planned_quantity != null
            ? ` · planned ${place.planned_quantity} ${place.measure_symbol}`
            : ""}
        </p>
      </div>
      <ErrorText>{error}</ErrorText>
      <Tabs tabs={TABS} value={tab} onChange={(key) => setSearchParams({ tab: key })} />
      {tab === "overview" && <Overview place={place} onChange={load} />}
      {tab === "board" && <TaskBoard projectId={place.id} />}
      {tab === "sheet" && <WorkSheet projectId={place.id} onChange={load} />}
      {tab === "timeline" && <TaskTimeline projectId={place.id} />}
      {tab === "teams" && <TeamsTab place={place} onChange={load} />}
      {tab === "reports" && <ReportsTab place={place} onChange={load} />}
      {tab === "stock" && <StockTab place={place} />}
    </div>
  );
}

export default ProjectPage;
