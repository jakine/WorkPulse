import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth, useRole } from "../context/AuthContext";
import AttachmentGrid from "./AttachmentGrid";
import MaterialUseForm from "./MaterialUseForm";
import { Badge, ErrorText, Field, formatWhen, styles } from "./ui";

const ISSUE_KINDS = [
  ["delay", "Delay"],
  ["weather", "Weather"],
  ["material", "Material missing"],
  ["access", "No access"],
  ["safety", "Safety"],
  ["other", "Other"],
];

const wide = { ...styles.input, width: "100%", boxSizing: "border-box" };
const crewBlock = {
  display: "grid",
  gap: "0.6rem",
  padding: "0.85rem 1rem",
  background: "var(--surface-2)",
  borderRadius: "var(--radius-sm)",
};

function savedHours(team) {
  const hours = {};
  for (const worker of team.crew) if (worker.present) hours[worker.worker] = String(Number(worker.hours));
  return hours;
}

function CrewBlock({ team, editable, onSave }) {
  const [chosen, setChosen] = useState(() => savedHours(team));

  useEffect(() => {
    setChosen(savedHours(team));
  }, [team]);

  const saved = savedHours(team);
  const changed =
    Object.keys(saved).length !== Object.keys(chosen).length || Object.entries(chosen).some(([id, hours]) => saved[id] !== hours);

  function toggle(worker) {
    setChosen((current) => {
      const next = { ...current };
      if (worker.worker in next) delete next[worker.worker];
      else next[worker.worker] = String(Number(worker.expected_hours));
      return next;
    });
  }

  function allPresent() {
    setChosen((current) => {
      const next = { ...current };
      for (const worker of team.crew) {
        const fullDayOff = worker.off && !worker.off.half_day;
        if (!(worker.worker in next) && !fullDayOff) next[worker.worker] = String(Number(worker.expected_hours));
      }
      return next;
    });
  }

  function save() {
    const hours = {};
    for (const [id, value] of Object.entries(chosen)) hours[id] = Number(value);
    onSave(team.team, Object.keys(chosen).map(Number), hours);
  }

  return (
    <div style={crewBlock}>
      <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
        <strong>
          {team.team_number} · {team.team_name}
        </strong>
        <Badge color={team.reported ? "var(--accent)" : "var(--warn)"}>{team.reported ? "Reported" : "No report yet"}</Badge>
        <span style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
          {team.present_count} of {team.crew.length} on site
        </span>
      </div>
      {team.crew.length === 0 ? (
        <p style={{ margin: 0, color: "var(--muted)" }}>No registered workers in this team.</p>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem 1.2rem" }}>
          {team.crew.map((worker) => (
            <span key={worker.worker} style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
              <label style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
                <input type="checkbox" checked={worker.worker in chosen} disabled={!editable} onChange={() => toggle(worker)} />
                {worker.name}
              </label>
              {!worker.member && <span style={{ color: "var(--muted)", fontSize: "0.8rem" }}>(other team)</span>}
              {worker.off && (
                <Badge color="var(--warn)">
                  {worker.off.code ? `Off · ${worker.off.name}` : "Off"}
                  {worker.off.half_day ? " (half day)" : ""}
                </Badge>
              )}
              {worker.worker in chosen && (
                <>
                  <input
                    type="number"
                    min="0.25"
                    max="24"
                    step="0.25"
                    value={chosen[worker.worker]}
                    disabled={!editable}
                    aria-label={`Hours for ${worker.name}`}
                    onChange={(e) => setChosen((current) => ({ ...current, [worker.worker]: e.target.value }))}
                    style={{ ...styles.input, width: "4rem", minWidth: 0, padding: "0.15rem 0.35rem" }}
                  />
                  <span style={{ color: "var(--muted)", fontSize: "0.8rem" }}>h</span>
                </>
              )}
            </span>
          ))}
        </div>
      )}
      {editable && team.crew.length > 0 && (
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <button type="button" style={styles.quiet} onClick={allPresent}>
            All present
          </button>
          <button type="button" style={styles.quiet} disabled={!changed} onClick={save}>
            Save crew
          </button>
        </div>
      )}
    </div>
  );
}

function DayLog({ day, workplaceId, workDate, onDay }) {
  const { user } = useAuth();
  const { canManage, isLead } = useRole();
  const [notes, setNotes] = useState({ weather: "", notes: "" });
  const [issue, setIssue] = useState({ kind: "delay", description: "", hours_lost: "" });
  const [reopening, setReopening] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const locked = day.status === "approved";
  const canWrite = (canManage || isLead) && !locked;
  const where = { workplace: Number(workplaceId), date: workDate };

  useEffect(() => {
    setNotes({ weather: day.log?.weather || "", notes: day.log?.notes || "" });
  }, [day.log]);

  async function run(action) {
    setError("");
    try {
      const next = await action();
      if (next) onDay(next);
    } catch (err) {
      setError(err.message);
    }
  }

  function reloadDay() {
    return api(`/daily-logs/day/?workplace=${workplaceId}&date=${workDate}`);
  }

  function saveCrew(teamId, workerIds, hours) {
    run(() =>
      api("/daily-logs/attendance/", { method: "PUT", body: { ...where, team: teamId, worker_ids: workerIds, hours } })
    );
  }

  function saveNotes(event) {
    event.preventDefault();
    run(() => api("/daily-logs/day/", { method: "PATCH", body: { ...where, ...notes } }));
  }

  function addIssue(event) {
    event.preventDefault();
    run(async () => {
      await api("/daily-log-issues/", {
        method: "POST",
        body: {
          workplace: where.workplace,
          work_date: workDate,
          kind: issue.kind,
          description: issue.description,
          hours_lost: issue.hours_lost || null,
        },
      });
      setIssue({ kind: issue.kind, description: "", hours_lost: "" });
      return reloadDay();
    });
  }

  function toggleResolved(row) {
    run(async () => {
      await api(`/daily-log-issues/${row.id}/`, { method: "PATCH", body: { resolved: !row.resolved } });
      return reloadDay();
    });
  }

  function approve() {
    run(() => api("/daily-logs/approve/", { method: "POST", body: where }));
  }

  function reopen(event) {
    event.preventDefault();
    run(async () => {
      const next = await api("/daily-logs/reopen/", { method: "POST", body: { ...where, reason } });
      setReason("");
      setReopening(false);
      return next;
    });
  }

  return (
    <div style={{ display: "grid", gap: "1.25rem" }}>
      <ErrorText>{error}</ErrorText>

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Crew on site</h2>
        {day.teams.length === 0 ? (
          <p style={{ margin: 0 }}>No team is placed on this project on this day.</p>
        ) : (
          <div style={{ display: "grid", gap: "0.75rem" }}>
            {day.teams.map((team) => (
              <CrewBlock
                key={team.team}
                team={team}
                editable={!locked && (canManage || (isLead && team.lead_user === user?.id))}
                onSave={saveCrew}
              />
            ))}
          </div>
        )}
      </div>

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Issues</h2>
        {day.issues.length === 0 ? (
          <p style={{ marginTop: 0, color: "var(--muted)" }}>No issues recorded for this day.</p>
        ) : (
          <table style={{ ...styles.table, marginBottom: "0.75rem" }}>
            <thead>
              <tr>
                <th style={styles.th}>Kind</th>
                <th style={styles.th}>What happened</th>
                <th style={styles.th}>Hours lost</th>
                <th style={styles.th}>By</th>
                <th style={styles.th}>Resolved</th>
              </tr>
            </thead>
            <tbody>
              {day.issues.map((row) => (
                <tr key={row.id}>
                  <td style={styles.td}>{row.kind_label}</td>
                  <td style={styles.td}>{row.description}</td>
                  <td style={styles.td}>{row.hours_lost ?? "—"}</td>
                  <td style={styles.td}>{row.created_by_email || "—"}</td>
                  <td style={styles.td}>
                    <input
                      type="checkbox"
                      checked={row.resolved}
                      disabled={!canWrite || (isLead && row.created_by !== user?.id)}
                      onChange={() => toggleResolved(row)}
                      aria-label={`Resolved: ${row.description}`}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {canWrite && (
          <form onSubmit={addIssue} style={styles.row}>
            <Field label="Kind">
              <select style={styles.input} value={issue.kind} onChange={(e) => setIssue({ ...issue, kind: e.target.value })}>
                {ISSUE_KINDS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="What happened">
              <input
                style={{ ...styles.input, minWidth: "16rem" }}
                value={issue.description}
                onChange={(e) => setIssue({ ...issue, description: e.target.value })}
                required
              />
            </Field>
            <Field label="Hours lost">
              <input
                style={styles.input}
                type="number"
                min="0"
                step="0.5"
                value={issue.hours_lost}
                onChange={(e) => setIssue({ ...issue, hours_lost: e.target.value })}
              />
            </Field>
            <button style={styles.button} type="submit">
              Add issue
            </button>
          </form>
        )}
      </div>

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Materials used</h2>
        {day.materials.length === 0 ? (
          <p style={{ marginTop: 0, color: "var(--muted)" }}>No material recorded for this day.</p>
        ) : (
          <table style={{ ...styles.table, marginBottom: "0.75rem" }}>
            <thead>
              <tr>
                <th style={styles.th}>Material</th>
                <th style={{ ...styles.th, textAlign: "right" }}>Used</th>
                <th style={styles.th}>For work type</th>
                <th style={styles.th}>By</th>
              </tr>
            </thead>
            <tbody>
              {day.materials.map((row) => (
                <tr key={row.id}>
                  <td style={styles.td}>{row.lot_item_name}</td>
                  <td style={{ ...styles.td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                    {row.quantity} {row.unit}
                  </td>
                  <td style={styles.td}>{row.scope_name || "—"}</td>
                  <td style={styles.td}>{row.recorded_by_email || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {canWrite && <MaterialUseForm workplaceId={workplaceId} date={workDate} onDone={() => reloadDay().then(onDay)} />}
      </div>

      <form onSubmit={saveNotes} style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Notes and weather</h2>
        <div style={{ display: "grid", gap: "0.75rem" }}>
          <Field label="Weather">
            <input
              style={wide}
              value={notes.weather}
              onChange={(e) => setNotes({ ...notes, weather: e.target.value })}
              placeholder="Sunny, 18 °C"
              disabled={!canWrite}
            />
          </Field>
          <Field label="Notes">
            <textarea
              style={{ ...wide, minHeight: "4.5rem" }}
              value={notes.notes}
              onChange={(e) => setNotes({ ...notes, notes: e.target.value })}
              placeholder="Deliveries, visitors, anything the office should know"
              disabled={!canWrite}
            />
          </Field>
          {canWrite && (
            <div>
              <button style={styles.button} type="submit">
                Save notes
              </button>
            </div>
          )}
        </div>
      </form>

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Photos</h2>
        {day.log ? (
          <AttachmentGrid targetType="sitelog.dailylog" targetId={day.log.id} canUpload={canWrite} locked={locked} />
        ) : canWrite ? (
          <button type="button" style={styles.quiet} onClick={() => run(() => api("/daily-logs/day/", { method: "PATCH", body: where }))}>
            Start adding photos
          </button>
        ) : (
          <p style={{ margin: 0, color: "var(--muted)" }}>No photos for this day.</p>
        )}
      </div>

      <div style={{ ...styles.card, display: "grid", gap: "0.75rem" }}>
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
          <h2 style={{ margin: 0 }}>Day status</h2>
          <Badge color={locked ? "var(--accent)" : "var(--warn)"}>{locked ? "Approved" : "Open"}</Badge>
        </div>
        <p style={{ margin: 0, color: "var(--muted)" }}>
          {locked
            ? `Approved by ${day.log?.approved_by_email || "a manager"} on ${formatWhen(day.log?.approved_at)}. Reports, crew, issues and photos are locked.`
            : "Open. Teams can still change reports, crew, issues and photos. Approve the day when it is complete."}
        </p>
        {canManage && !locked && (
          <div>
            <button type="button" style={styles.button} onClick={approve}>
              Approve day
            </button>
          </div>
        )}
        {canManage && locked && !reopening && (
          <div>
            <button type="button" style={styles.quiet} onClick={() => setReopening(true)}>
              Reopen day
            </button>
          </div>
        )}
        {canManage && locked && reopening && (
          <form onSubmit={reopen} style={styles.row}>
            <Field label="Why are you reopening it?">
              <input style={{ ...styles.input, minWidth: "18rem" }} value={reason} onChange={(e) => setReason(e.target.value)} required />
            </Field>
            <button style={styles.button} type="submit">
              Reopen
            </button>
            <button style={styles.quiet} type="button" onClick={() => setReopening(false)}>
              Cancel
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

export default DayLog;
