import { useCallback, useEffect, useMemo, useState } from "react";
import { api, apiList } from "../api/client";
import { useAuth, useRole } from "../context/AuthContext";
import ReportCalendar, { formatLongDay, todayIso, weekDays } from "./ReportCalendar";
import { ErrorText, Field, styles } from "./ui";

function isoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function endOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

function daysInRange(start, end) {
  const days = [];
  for (let cursor = new Date(start); cursor <= end; cursor = addDays(cursor, 1)) {
    days.push(isoDate(cursor));
  }
  return days;
}

function formatDay(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function isWeekend(value) {
  const day = new Date(`${value}T00:00:00`).getDay();
  return day === 0 || day === 6;
}

function quantityValue(report) {
  if (!report || report.quantity == null || report.quantity === "") return "";
  const number = Number(report.quantity);
  return Number.isNaN(number) ? "" : String(number);
}

function columnLabel(column) {
  if (column.label) return column.label;
  if (column.kind === "work_type") return column.scope_name || "Work type";
  if (column.kind === "team") {
    return column.team_number != null ? `${column.team_number} · ${column.team_name}` : column.team_name || "Team";
  }
  return column.name || "Text";
}

function CellInput({ value, label, disabled, pending, type = "number", onSave }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => {
    setDraft(value);
  }, [value]);

  function commit() {
    const next = draft.trim();
    if (next === value) return;
    onSave(next);
  }

  return (
    <input
      type={type}
      min={type === "number" ? "0" : undefined}
      step={type === "number" ? "0.01" : undefined}
      disabled={disabled || pending}
      value={draft}
      aria-label={label}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") event.currentTarget.blur();
      }}
      style={{
        ...styles.input,
        width: type === "text" ? "10rem" : "6.5rem",
        background: disabled ? "var(--surface-2)" : "var(--surface)",
        color: "var(--ink)",
        border: "1px solid var(--line)",
        opacity: pending ? 0.6 : 1,
      }}
    />
  );
}

function WorkSheet({ projectId, onChange }) {
  const { user } = useAuth();
  const { canManage, isLead } = useRole();
  const [projects, setProjects] = useState([]);
  const [chosenId, setChosenId] = useState(projectId ? String(projectId) : "");
  const [place, setPlace] = useState(null);
  const [reports, setReports] = useState([]);
  const [selectedTeam, setSelectedTeam] = useState("");
  const [selectedScope, setSelectedScope] = useState("");
  const [rangeStep, setRangeStep] = useState("day");
  const [workDate, setWorkDate] = useState(todayIso);
  const [pendingKey, setPendingKey] = useState("");
  const [error, setError] = useState("");
  const [showSetup, setShowSetup] = useState(false);
  const [columnForm, setColumnForm] = useState({ kind: "work_type", scope: "", team: "", name: "" });

  const activeId = projectId || chosenId;

  const load = useCallback(async (id) => {
    if (!id) {
      setPlace(null);
      setReports([]);
      return;
    }
    const [detail, rows] = await Promise.all([
      api(`/projects/${id}/`),
      apiList(`/site-reports/?workplace=${id}`),
    ]);
    setPlace(detail);
    setReports(rows);
  }, []);

  useEffect(() => {
    if (projectId) return;
    apiList("/projects/")
      .then(setProjects)
      .catch((err) => setError(err.message));
  }, [projectId]);

  useEffect(() => {
    if (!activeId) {
      setPlace(null);
      setReports([]);
      return;
    }
    setPlace(null);
    load(activeId).catch((err) => setError(err.message));
  }, [activeId, load]);

  useEffect(() => {
    if (canManage && place && (place.sheet_columns || []).length === 0) {
      setShowSetup(true);
    }
  }, [canManage, place]);

  const teams = useMemo(() => place?.teams || [], [place]);
  const scopes = useMemo(() => place?.scopes || [], [place]);
  const columns = useMemo(() => place?.sheet_columns || [], [place]);
  const texts = useMemo(() => place?.sheet_texts || [], [place]);
  const leadTeam = teams.find((row) => row.lead_user === user?.id);
  const leadTeamId = leadTeam ? String(leadTeam.team) : "";
  const needsTeam = columns.some((column) => column.kind === "work_type");
  const needsScope = columns.some((column) => column.kind === "team");

  useEffect(() => {
    if (!place) return;
    setSelectedTeam((current) => {
      if (isLead && leadTeamId) return leadTeamId;
      if (current && teams.some((row) => String(row.team) === current)) return current;
      return teams[0] ? String(teams[0].team) : "";
    });
    setSelectedScope((current) => {
      if (current && scopes.some((scope) => String(scope.id) === current)) return current;
      return scopes[0] ? String(scopes[0].id) : "";
    });
  }, [place, isLead, leadTeamId, teams, scopes]);

  const days = useMemo(() => {
    if (rangeStep === "month") {
      const date = new Date(`${workDate}T00:00:00`);
      return daysInRange(startOfMonth(date), endOfMonth(date));
    }
    if (rangeStep === "week") return weekDays(workDate);
    return [workDate];
  }, [rangeStep, workDate]);

  const [approvedDates, setApprovedDates] = useState(() => new Set());
  const firstDay = days[0];
  const lastDay = days[days.length - 1];

  useEffect(() => {
    if (!activeId) {
      setApprovedDates(new Set());
      return;
    }
    apiList(`/daily-logs/?workplace=${activeId}&status=approved&from=${firstDay}&to=${lastDay}`)
      .then((rows) => setApprovedDates(new Set(rows.map((row) => row.work_date))))
      .catch((err) => setError(err.message));
  }, [activeId, firstDay, lastDay]);

  function canEditTeam(teamId) {
    if (!teamId) return canManage;
    if (canManage) return true;
    if (isLead && leadTeamId && String(teamId) === leadTeamId) return true;
    return false;
  }

  function reportFor(date, teamId, scopeId) {
    return reports.find(
      (row) => row.work_date === date && row.team === Number(teamId) && row.scope === Number(scopeId)
    );
  }

  function textFor(date, columnId) {
    const row = texts.find((cell) => cell.work_date === date && cell.column === columnId);
    return row?.text || "";
  }

  function teamDone(teamId, scopeId) {
    return reports
      .filter((row) => row.team === Number(teamId) && row.scope === Number(scopeId))
      .reduce((total, row) => total + Number(row.quantity || 0), 0);
  }

  function cellTarget(column) {
    if (column.kind === "work_type") return { teamId: Number(selectedTeam), scopeId: column.scope };
    if (column.kind === "team") return { teamId: column.team, scopeId: Number(selectedScope) };
    return { teamId: null, scopeId: null };
  }

  async function saveCell(date, column, value) {
    if (!place) return;
    const key = `${date}:${column.id}`;
    setError("");
    setPendingKey(key);
    try {
      const body = { column: column.id, work_date: date };
      if (column.kind === "text") {
        body.text = value;
      } else {
        const target = cellTarget(column);
        if (column.kind === "work_type") body.team = target.teamId;
        if (column.kind === "team") body.scope = target.scopeId;
        body.quantity = value === "" ? null : value;
      }
      await api(`/projects/${place.id}/sheet/`, { method: "POST", body });
      await load(place.id);
      if (onChange) await onChange();
    } catch (err) {
      setError(err.message);
    } finally {
      setPendingKey("");
    }
  }

  async function addColumn(event) {
    event.preventDefault();
    if (!place) return;
    setError("");
    try {
      await api("/sheet-columns/", {
        method: "POST",
        body: {
          workplace: place.id,
          kind: columnForm.kind,
          scope: columnForm.kind === "work_type" && columnForm.scope ? Number(columnForm.scope) : null,
          team: columnForm.kind === "team" && columnForm.team ? Number(columnForm.team) : null,
          name: columnForm.kind === "text" ? columnForm.name : "",
        },
      });
      setColumnForm({ kind: columnForm.kind, scope: "", team: "", name: "" });
      await load(place.id);
      if (onChange) await onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  async function moveColumn(index, direction) {
    const next = columns.map((column) => column.id);
    const swap = index + direction;
    if (swap < 0 || swap >= next.length) return;
    [next[index], next[swap]] = [next[swap], next[index]];
    setError("");
    try {
      await api("/sheet-columns/reorder/", { method: "POST", body: { workplace: place.id, ids: next } });
      await load(place.id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function removeColumn(column) {
    if (!window.confirm(`Remove column “${columnLabel(column)}”?`)) return;
    setError("");
    try {
      await api(`/sheet-columns/${column.id}/`, { method: "DELETE" });
      await load(place.id);
      if (onChange) await onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  const rangeLabel =
    rangeStep === "day"
      ? formatLongDay(workDate)
      : days.length > 0
        ? `${formatDay(days[0])} – ${formatDay(days[days.length - 1])}`
        : "";
  const canFill =
    columns.length > 0 &&
    (!needsTeam || selectedTeam) &&
    (!needsScope || selectedScope) &&
    (!needsTeam || teams.length > 0);

  return (
    <div style={{ display: "grid", gap: "1.25rem" }}>
      <div style={{ ...styles.card, ...styles.row }}>
        {!projectId && (
          <Field label="Project">
            <select style={styles.input} value={chosenId} onChange={(event) => setChosenId(event.target.value)}>
              <option value="">Choose a project</option>
              {projects.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        {needsTeam && (
          <Field label="Team filling work types">
            <select
              style={styles.input}
              value={selectedTeam}
              disabled={isLead && Boolean(leadTeamId)}
              onChange={(event) => setSelectedTeam(event.target.value)}
            >
              <option value="">Choose</option>
              {teams.map((row) => (
                <option key={row.id} value={row.team}>
                  {row.team_number} · {row.team_name}
                </option>
              ))}
            </select>
          </Field>
        )}
        {needsScope && (
          <Field label="Work type for team columns">
            <select style={styles.input} value={selectedScope} onChange={(event) => setSelectedScope(event.target.value)}>
              <option value="">Choose</option>
              {scopes.map((scope) => (
                <option key={scope.id} value={scope.id}>
                  {scope.work_type_name} ({scope.measure_symbol})
                </option>
              ))}
            </select>
          </Field>
        )}
        {canManage && place && (
          <button type="button" style={styles.quiet} onClick={() => setShowSetup((value) => !value)}>
            {showSetup ? "Hide columns" : "Set up columns"}
          </button>
        )}
      </div>
      <ErrorText>{error}</ErrorText>
      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Choose a day</h2>
        <p className="lede" style={{ marginTop: "0.35rem" }}>
          {rangeStep === "day"
            ? "Defaults to today. Tap another day to fill that report."
            : "Pick a week or month, then fill each day in the table."}
        </p>
        <ReportCalendar
          value={workDate}
          mode={rangeStep}
          markedDates={[...new Set(reports.map((row) => row.work_date))]}
          onChange={setWorkDate}
          onModeChange={setRangeStep}
        />
      </div>
      {!activeId && <p>Choose a project above, then fill the selected day in the table.</p>}
      {place && columns.length === 0 && (
        <p>Add columns to set up this sheet. A column can be a work type, a team, or a text note.</p>
      )}
      {canManage && place && showSetup && (
        <>
          <form onSubmit={addColumn} style={styles.card}>
            <h2 style={{ marginTop: 0 }}>Add a column</h2>
            <div style={styles.row}>
              <Field label="Type">
                <select
                  style={styles.input}
                  value={columnForm.kind}
                  onChange={(event) => setColumnForm({ ...columnForm, kind: event.target.value })}
                >
                  <option value="work_type">Work type</option>
                  <option value="team">Team</option>
                  <option value="text">Text</option>
                </select>
              </Field>
              {columnForm.kind === "work_type" && (
                <Field label="Work type">
                  <select
                    style={styles.input}
                    value={columnForm.scope}
                    onChange={(event) => setColumnForm({ ...columnForm, scope: event.target.value })}
                    required
                  >
                    <option value="">Choose</option>
                    {scopes.map((scope) => (
                      <option key={scope.id} value={scope.id}>
                        {scope.work_type_name} ({scope.measure_symbol})
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              {columnForm.kind === "team" && (
                <Field label="Team">
                  <select
                    style={styles.input}
                    value={columnForm.team}
                    onChange={(event) => setColumnForm({ ...columnForm, team: event.target.value })}
                    required
                  >
                    <option value="">Choose</option>
                    {teams.map((row) => (
                      <option key={row.id} value={row.team}>
                        {row.team_number} · {row.team_name}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              {columnForm.kind === "text" && (
                <Field label="Column name">
                  <input
                    style={styles.input}
                    value={columnForm.name}
                    onChange={(event) => setColumnForm({ ...columnForm, name: event.target.value })}
                    required
                  />
                </Field>
              )}
              <button style={styles.button} type="submit">
                Add column
              </button>
            </div>
          </form>
          {columns.length > 0 && (
            <div style={styles.card}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Order</th>
                    <th style={styles.th}>Type</th>
                    <th style={styles.th}>Column</th>
                    <th style={styles.th}></th>
                  </tr>
                </thead>
                <tbody>
                  {columns.map((column, index) => (
                    <tr key={column.id}>
                      <td style={styles.td}>
                        <button type="button" style={styles.quiet} onClick={() => moveColumn(index, -1)} disabled={index === 0}>
                          Up
                        </button>{" "}
                        <button
                          type="button"
                          style={styles.quiet}
                          onClick={() => moveColumn(index, 1)}
                          disabled={index === columns.length - 1}
                        >
                          Down
                        </button>
                      </td>
                      <td style={styles.td}>{column.kind === "work_type" ? "Work type" : column.kind === "team" ? "Team" : "Text"}</td>
                      <td style={styles.td}>
                        {columnLabel(column)}
                        {column.measure_symbol ? ` (${column.measure_symbol})` : ""}
                      </td>
                      <td style={styles.td}>
                        <button type="button" style={styles.danger} onClick={() => removeColumn(column)}>
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      {place && columns.length > 0 && (
        <div style={{ ...styles.card, overflowX: "auto" }}>
          <h2 style={{ marginTop: 0 }}>Fill {rangeLabel}</h2>
          {!canFill && <p>Choose the team or work type above, then type the amount on each day.</p>}
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Day</th>
                {columns.map((column) => (
                  <th key={column.id} style={styles.th}>
                    {columnLabel(column)}
                    {column.measure_symbol ? ` (${column.measure_symbol})` : ""}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {days.map((date) => (
                <tr key={date} style={{ background: isWeekend(date) ? "var(--surface-2)" : "transparent" }}>
                  <td style={{ ...styles.td, whiteSpace: "nowrap", fontWeight: 600 }}>
                    {formatDay(date)}
                    {approvedDates.has(date) && (
                      <span style={{ marginLeft: "0.4rem", fontSize: "0.72rem", fontWeight: 600, color: "var(--accent)" }}>
                        Approved
                      </span>
                    )}
                  </td>
                  {columns.map((column) => {
                    const target = cellTarget(column);
                    const report = column.kind === "text" ? null : reportFor(date, target.teamId, target.scopeId);
                    const disabled =
                      approvedDates.has(date) ||
                      (column.kind === "text"
                        ? false
                        : !canEditTeam(target.teamId) || !target.teamId || !target.scopeId);
                    return (
                      <td key={column.id} style={styles.td}>
                        <CellInput
                          type={column.kind === "text" ? "text" : "number"}
                          value={column.kind === "text" ? textFor(date, column.id) : quantityValue(report)}
                          label={columnLabel(column)}
                          disabled={disabled}
                          pending={pendingKey === `${date}:${column.id}`}
                          onSave={(value) => saveCell(date, column, value)}
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td style={{ ...styles.td, fontWeight: 700 }}>Done / planned / left</td>
                {columns.map((column) => {
                  if (column.kind === "work_type") {
                    return (
                      <td key={column.id} style={{ ...styles.td, color: "var(--muted)" }}>
                        {column.done_quantity} / {column.planned_quantity} / {column.remaining_quantity}{" "}
                        {column.measure_symbol}
                      </td>
                    );
                  }
                  if (column.kind === "team") {
                    const scope = scopes.find((row) => row.id === Number(selectedScope));
                    return (
                      <td key={column.id} style={{ ...styles.td, color: "var(--muted)" }}>
                        {teamDone(column.team, selectedScope)} / {scope?.planned_quantity ?? "—"} /{" "}
                        {scope?.remaining_quantity ?? "—"} {scope?.measure_symbol || ""}
                      </td>
                    );
                  }
                  return (
                    <td key={column.id} style={{ ...styles.td, color: "var(--muted)" }}>
                      Text
                    </td>
                  );
                })}
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}

export default WorkSheet;
