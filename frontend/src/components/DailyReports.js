import { useCallback, useEffect, useMemo, useState } from "react";
import { api, apiList } from "../api/client";
import DayLog from "./DayLog";
import ReportCalendar, { formatLongDay, todayIso, weekDays } from "./ReportCalendar";
import { ErrorText, Field, styles } from "./ui";

function DailyReports({ workplaceId, place: initialPlace, onPlaceChange }) {
  const [place, setPlace] = useState(initialPlace || null);
  const [reports, setReports] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [mode, setMode] = useState("day");
  const [workDate, setWorkDate] = useState(todayIso);
  const [form, setForm] = useState({
    days: "1",
    team: "",
    task: "",
    scope: "",
    quantity: "",
    note: "",
  });
  const [day, setDay] = useState(null);
  const [error, setError] = useState("");

  const reloadDay = useCallback(async () => {
    if (!workplaceId || mode !== "day") {
      setDay(null);
      return;
    }
    setDay(await api(`/daily-logs/day/?workplace=${workplaceId}&date=${workDate}`));
  }, [workplaceId, workDate, mode]);

  useEffect(() => {
    reloadDay().catch((err) => setError(err.message));
  }, [reloadDay]);

  const reload = useCallback(async () => {
    if (!workplaceId) {
      setReports([]);
      setTasks([]);
      return;
    }
    const [detail, rows, taskRows] = await Promise.all([
      api(`/projects/${workplaceId}/`),
      apiList(`/site-reports/?workplace=${workplaceId}`),
      apiList(`/tasks/?project=${workplaceId}`),
    ]);
    setPlace(detail);
    setReports(rows);
    setTasks(taskRows);
  }, [workplaceId]);

  useEffect(() => {
    setPlace(initialPlace || null);
  }, [initialPlace]);

  useEffect(() => {
    if (!workplaceId) {
      setPlace(null);
      setReports([]);
      setTasks([]);
      return;
    }
    setPlace(null);
    setReports([]);
    setTasks([]);
    reload().catch((err) => setError(err.message));
  }, [workplaceId, reload]);

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function fillReport(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/site-reports/", {
        method: "POST",
        body: {
          workplace: Number(workplaceId),
          team: Number(form.team),
          task: form.task ? Number(form.task) : null,
          scope: form.scope ? Number(form.scope) : null,
          work_date: workDate,
          days: form.days,
          quantity: form.quantity,
          note: form.note,
        },
      });
      setForm({ days: "1", team: form.team, task: "", scope: form.scope, quantity: "", note: "" });
      await Promise.all([reload(), reloadDay()]);
      if (onPlaceChange) onPlaceChange();
    } catch (err) {
      setError(err.message);
    }
  }

  const selectedTask = tasks.find((task) => String(task.id) === String(form.task));
  const selectedScope = (place?.scopes || []).find((scope) => String(scope.id) === String(form.scope));
  const symbol = selectedScope?.measure_symbol || selectedTask?.measure_symbol || place?.measure_symbol;
  const markedDates = useMemo(() => [...new Set(reports.map((row) => row.work_date))], [reports]);
  const visibleDates = mode === "week" ? weekDays(workDate) : [workDate];
  const visibleReports = reports.filter((row) => visibleDates.includes(row.work_date));

  if (!place) return <ErrorText>{error || "Loading..."}</ErrorText>;

  return (
    <div style={{ display: "grid", gap: "1.25rem" }}>
      <ErrorText>{error}</ErrorText>
      <div style={styles.card}>
        <div style={{ ...styles.row, justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h2 style={{ margin: 0 }}>Choose a day</h2>
            <p className="lede" style={{ marginTop: "0.35rem" }}>
              {mode === "week" ? "Reporting starts on the day you pick inside the selected week." : "Defaults to today. Pick another day on the calendar."}
            </p>
          </div>
        </div>
        <ReportCalendar
          value={workDate}
          mode={mode}
          markedDates={markedDates}
          onChange={setWorkDate}
          onModeChange={setMode}
        />
      </div>

      {day?.status === "approved" ? (
        <div style={styles.card}>
          <h2 style={{ marginTop: 0 }}>{formatLongDay(workDate)} is approved</h2>
          <p style={{ margin: 0 }}>Reports for this day are locked. A manager can reopen the day at the bottom of this page.</p>
        </div>
      ) : (
      <form onSubmit={fillReport} style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Add report · {formatLongDay(workDate)}</h2>
        {(place.teams || []).length === 0 && <p>Place a team on this project before filling a report.</p>}
        <div style={styles.row}>
          <Field label="Team">
            <select style={styles.input} value={form.team} onChange={(e) => setField("team", e.target.value)} required>
              <option value="">Choose</option>
              {(place.teams || []).map((row) => (
                <option key={row.id} value={row.team}>
                  {row.team_number} · {row.team_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Work type">
            <select style={styles.input} value={form.scope} onChange={(e) => setField("scope", e.target.value)}>
              <option value="">None</option>
              {(place.scopes || []).map((scope) => (
                <option key={scope.id} value={scope.id}>
                  {scope.work_type_name} ({scope.measure_symbol})
                </option>
              ))}
            </select>
          </Field>
          <Field label="Task (optional)">
            <select style={styles.input} value={form.task} onChange={(e) => setField("task", e.target.value)}>
              <option value="">No task</option>
              {tasks.map((task) => (
                <option key={task.id} value={task.id}>
                  {task.key} · {task.title}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Days worked">
            <input
              style={styles.input}
              type="number"
              min="0.5"
              step="0.5"
              value={form.days}
              onChange={(e) => setField("days", e.target.value)}
              required
            />
          </Field>
          <Field label={symbol ? `Amount (${symbol})` : "Amount"}>
            <input
              style={styles.input}
              type="number"
              min="0.01"
              step="0.01"
              value={form.quantity}
              onChange={(e) => setField("quantity", e.target.value)}
              required
            />
          </Field>
          <Field label="Note">
            <input style={styles.input} value={form.note} onChange={(e) => setField("note", e.target.value)} />
          </Field>
          <button style={styles.button} type="submit">
            Add report
          </button>
        </div>
      </form>
      )}

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>{mode === "week" ? "Reports this week" : "Reports this day"}</h2>
        {visibleReports.length === 0 ? (
          <p>No reports for {mode === "week" ? "this week" : formatLongDay(workDate)} yet.</p>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Date</th>
                <th style={styles.th}>Team</th>
                <th style={styles.th}>Work type</th>
                <th style={styles.th}>Task</th>
                <th style={styles.th}>Days</th>
                <th style={styles.th}>Done</th>
                <th style={styles.th}>Note</th>
              </tr>
            </thead>
            <tbody>
              {visibleReports.map((row) => (
                <tr key={row.id}>
                  <td style={styles.td}>{row.work_date}</td>
                  <td style={styles.td}>{row.team_name ? `${row.team_number} · ${row.team_name}` : "—"}</td>
                  <td style={styles.td}>{row.scope_name || "—"}</td>
                  <td style={styles.td}>{row.task_title || "—"}</td>
                  <td style={styles.td}>{row.days}</td>
                  <td style={styles.td}>
                    {row.quantity}
                    {row.measure_symbol ? ` ${row.measure_symbol}` : ""}
                  </td>
                  <td style={styles.td}>{row.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {mode === "day" && day && (
        <DayLog
          day={day}
          workplaceId={workplaceId}
          workDate={workDate}
          onDay={(next) => {
            setDay(next);
            reload().catch((err) => setError(err.message));
          }}
        />
      )}
    </div>
  );
}

export default DailyReports;
