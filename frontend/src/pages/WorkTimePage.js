import { useCallback, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api, apiList } from "../api/client";
import { Badge, ErrorText, Field, PageHeader, companyToday, formatDay, styles } from "../components/ui";
import { WEEKDAYS, hoursLabel, versionOn } from "../components/hours";
import { useAuth, useRole } from "../context/AuthContext";

const emptyHours = { mon: "8", tue: "8", wed: "8", thu: "8", fri: "8", sat: "0", sun: "0", day_hours: "8" };
const hourInput = { ...styles.input, width: "4.2rem", minWidth: 0 };

function hoursBody(form) {
  const body = { day_hours: Number(form.day_hours || 8) };
  for (const [key] of WEEKDAYS) body[key] = Number(form[key] || 0);
  return body;
}

function HoursInputs({ form, onChange }) {
  return (
    <>
      {WEEKDAYS.map(([key, label]) => (
        <Field key={key} label={label}>
          <input
            style={hourInput}
            type="number"
            min="0"
            max="24"
            step="0.5"
            value={form[key]}
            onChange={(e) => onChange(key, e.target.value)}
          />
        </Field>
      ))}
      <Field label="Full day (h)">
        <input
          style={hourInput}
          type="number"
          min="0.5"
          max="24"
          step="0.5"
          value={form.day_hours}
          onChange={(e) => onChange("day_hours", e.target.value)}
          title="Counts as a full day on days the schedule has no hours"
        />
      </Field>
    </>
  );
}

function Schedules({ schedules, today, run }) {
  const [form, setForm] = useState({ name: "", ...emptyHours });
  const [changing, setChanging] = useState(null);

  function startChange(schedule) {
    const current = versionOn(schedule.versions, today) || schedule.versions[0];
    const next = { valid_from: today, day_hours: String(Number(current.day_hours)) };
    for (const [key] of WEEKDAYS) next[key] = String(Number(current[key]));
    setChanging({ id: schedule.id, ...next });
  }

  async function addSchedule(event) {
    event.preventDefault();
    const ok = await run(() => api("/schedules/", { method: "POST", body: { name: form.name, ...hoursBody(form) } }));
    if (ok) setForm({ name: "", ...emptyHours });
  }

  async function saveChange(event) {
    event.preventDefault();
    const ok = await run(() =>
      api(`/schedules/${changing.id}/versions/`, {
        method: "POST",
        body: { valid_from: changing.valid_from, ...hoursBody(changing) },
      })
    );
    if (ok) setChanging(null);
  }

  async function remove(schedule) {
    if (!window.confirm(`Delete the schedule "${schedule.name}"?`)) return;
    await run(() => api(`/schedules/${schedule.id}/`, { method: "DELETE" }));
  }

  return (
    <div style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Schedules</h2>
      <p style={{ marginTop: 0 }}>
        Hours per weekday. Everyone follows the company default unless they have their own schedule. Changing hours
        starts from a date, so earlier days keep the hours they had.
      </p>
      <div style={{ overflowX: "auto" }}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Schedule</th>
              {WEEKDAYS.map(([key, label]) => (
                <th key={key} style={{ ...styles.th, textAlign: "right" }}>
                  {label}
                </th>
              ))}
              <th style={{ ...styles.th, textAlign: "right" }}>Week</th>
              <th style={styles.th}>Used by</th>
              <th style={styles.th} />
            </tr>
          </thead>
          <tbody>
            {schedules.map((schedule) => {
              const current = versionOn(schedule.versions, today) || schedule.versions[0];
              const later = schedule.versions.filter((version) => version.valid_from && version.valid_from > today);
              return (
                <tr key={schedule.id}>
                  <td style={styles.td}>
                    <strong>{schedule.name}</strong> {schedule.is_default && <Badge>Company default</Badge>}
                    {later.length > 0 && (
                      <div style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
                        Changes on {later.map((version) => formatDay(version.valid_from)).join(", ")}
                      </div>
                    )}
                  </td>
                  {WEEKDAYS.map(([key]) => (
                    <td key={key} style={{ ...styles.td, textAlign: "right" }}>
                      {current ? hoursLabel(current[key]) : "–"}
                    </td>
                  ))}
                  <td style={{ ...styles.td, textAlign: "right" }}>{current ? Number(current.week_hours) : "–"}</td>
                  <td style={styles.td}>
                    {schedule.is_default ? "Everyone else" : `${schedule.worker_count} worker${schedule.worker_count === 1 ? "" : "s"}`}
                  </td>
                  <td style={{ ...styles.td, whiteSpace: "nowrap" }}>
                    <button type="button" style={styles.quiet} onClick={() => startChange(schedule)}>
                      Change hours
                    </button>{" "}
                    {!schedule.is_default && schedule.worker_count === 0 && (
                      <button type="button" style={styles.danger} onClick={() => remove(schedule)}>
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {changing && (
        <form onSubmit={saveChange} style={{ ...styles.row, marginTop: "1rem" }}>
          <Field label="New hours from">
            <input
              style={styles.input}
              type="date"
              value={changing.valid_from}
              onChange={(e) => setChanging({ ...changing, valid_from: e.target.value })}
              required
            />
          </Field>
          <HoursInputs form={changing} onChange={(key, value) => setChanging({ ...changing, [key]: value })} />
          <button style={styles.button} type="submit">
            Save hours
          </button>
          <button style={styles.quiet} type="button" onClick={() => setChanging(null)}>
            Cancel
          </button>
        </form>
      )}

      <form onSubmit={addSchedule} style={{ ...styles.row, marginTop: "1rem" }}>
        <Field label="New schedule">
          <input
            style={styles.input}
            value={form.name}
            placeholder="e.g. Six days"
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
        </Field>
        <HoursInputs form={form} onChange={(key, value) => setForm({ ...form, [key]: value })} />
        <button style={styles.button} type="submit">
          Add schedule
        </button>
      </form>
    </div>
  );
}

function ApplySchedule({ schedules, teams, workers, today, run }) {
  const [form, setForm] = useState({ schedule: "", target: "team", team: "", worker_ids: [], start_date: today });

  function toggleWorker(id) {
    setForm((current) => ({
      ...current,
      worker_ids: current.worker_ids.includes(id)
        ? current.worker_ids.filter((value) => value !== id)
        : [...current.worker_ids, id],
    }));
  }

  async function submit(event) {
    event.preventDefault();
    const body = { start_date: form.start_date };
    if (form.target === "everyone") body.everyone = true;
    if (form.target === "team") body.team = Number(form.team);
    if (form.target === "workers") body.worker_ids = form.worker_ids;
    const path = form.schedule === "default" ? "/schedules/reset/" : `/schedules/${form.schedule}/apply/`;
    const ok = await run(() => api(path, { method: "POST", body }));
    if (ok) setForm({ ...form, worker_ids: [] });
  }

  return (
    <form onSubmit={submit} style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Apply a schedule</h2>
      <p style={{ marginTop: 0 }}>
        From the chosen day. Applying to everyone changes the company default; workers with their own schedule keep it.
      </p>
      <div style={styles.row}>
        <Field label="Schedule">
          <select
            style={styles.input}
            value={form.schedule}
            onChange={(e) => setForm({ ...form, schedule: e.target.value })}
            required
          >
            <option value="" disabled>
              Choose
            </option>
            {schedules.map((schedule) => (
              <option key={schedule.id} value={schedule.id}>
                {schedule.name}
              </option>
            ))}
            {form.target !== "everyone" && <option value="default">Back to the company default</option>}
          </select>
        </Field>
        <Field label="For">
          <select style={styles.input} value={form.target} onChange={(e) => setForm({ ...form, target: e.target.value })}>
            <option value="team">A team</option>
            <option value="workers">Chosen workers</option>
            <option value="everyone">Everyone (company default)</option>
          </select>
        </Field>
        {form.target === "team" && (
          <Field label="Team">
            <select style={styles.input} value={form.team} onChange={(e) => setForm({ ...form, team: e.target.value })} required>
              <option value="" disabled>
                Choose
              </option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.number} · {team.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field label="From">
          <input
            style={styles.input}
            type="date"
            value={form.start_date}
            onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            required
          />
        </Field>
        <button style={styles.button} type="submit" disabled={form.target === "workers" && form.worker_ids.length === 0}>
          Apply
        </button>
      </div>
      {form.target === "workers" && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem 1.1rem", marginTop: "0.8rem" }}>
          {workers.map((worker) => (
            <label key={worker.id} style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
              <input type="checkbox" checked={form.worker_ids.includes(worker.id)} onChange={() => toggleWorker(worker.id)} />
              {worker.name}
            </label>
          ))}
        </div>
      )}
    </form>
  );
}

function Holidays({ today, run }) {
  const thisYear = Number(today.slice(0, 4));
  const [year, setYear] = useState(thisYear);
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ date: "", name: "" });

  const load = useCallback(async () => {
    setRows(await apiList(`/holidays/?year=${year}`));
  }, [year]);

  useEffect(() => {
    load().catch(() => setRows([]));
  }, [load]);

  async function act(action) {
    if (await run(action)) await load();
  }

  async function add(event) {
    event.preventDefault();
    await act(() => api("/holidays/", { method: "POST", body: form }));
    setForm({ date: "", name: "" });
  }

  return (
    <div style={styles.card}>
      <div style={{ display: "flex", gap: "0.8rem", alignItems: "center", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Holidays</h2>
        <select style={{ ...styles.input, width: "auto" }} value={year} onChange={(e) => setYear(Number(e.target.value))}>
          {[thisYear - 1, thisYear, thisYear + 1].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <button
          type="button"
          style={styles.quiet}
          onClick={() => act(() => api("/holidays/copy-year/", { method: "POST", body: { from_year: year - 1, to_year: year } }))}
        >
          Copy from {year - 1}
        </button>
      </div>
      <p>Nobody is expected to work on a holiday. Copying keeps the same dates, so check holidays that move each year.</p>
      {rows.length === 0 ? (
        <p style={{ color: "var(--muted)" }}>No holidays in {year}.</p>
      ) : (
        <table style={styles.table}>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td style={{ ...styles.td, width: "11rem" }}>{formatDay(row.date)}</td>
                <td style={styles.td}>{row.name}</td>
                <td style={{ ...styles.td, textAlign: "right" }}>
                  <button type="button" style={styles.danger} onClick={() => act(() => api(`/holidays/${row.id}/`, { method: "DELETE" }))}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form onSubmit={add} style={{ ...styles.row, marginTop: "0.8rem" }}>
        <Field label="Date">
          <input style={styles.input} type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} required />
        </Field>
        <Field label="Name">
          <input style={styles.input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </Field>
        <button style={styles.button} type="submit">
          Add holiday
        </button>
      </form>
    </div>
  );
}

const CYCLES = [
  ["weekly", "Weekly"],
  ["two_weeks", "Every two weeks"],
  ["monthly", "Monthly"],
];

function PayGroups({ teams, workers, today, run }) {
  const [groups, setGroups] = useState([]);
  const [form, setForm] = useState({ name: "", cycle: "weekly", anchor_date: "" });
  const [move, setMove] = useState({ group: "", target: "workers", team: "", worker_ids: [], start_date: today });

  const load = useCallback(async () => {
    setGroups(await apiList("/pay-groups/"));
  }, []);

  useEffect(() => {
    load().catch(() => setGroups([]));
  }, [load]);

  async function act(action) {
    const ok = await run(action);
    if (ok) await load();
    return ok;
  }

  async function add(event) {
    event.preventDefault();
    const body = { name: form.name, cycle: form.cycle, anchor_date: form.cycle === "two_weeks" && form.anchor_date ? form.anchor_date : null };
    if (await act(() => api("/pay-groups/", { method: "POST", body }))) setForm({ name: "", cycle: "weekly", anchor_date: "" });
  }

  async function submitMove(event) {
    event.preventDefault();
    const body = { start_date: move.start_date };
    if (move.target === "team") body.team = Number(move.team);
    else body.worker_ids = move.worker_ids;
    if (await act(() => api(`/pay-groups/${move.group}/assign/`, { method: "POST", body }))) setMove({ ...move, worker_ids: [] });
  }

  function toggleWorker(id) {
    setMove((current) => ({
      ...current,
      worker_ids: current.worker_ids.includes(id) ? current.worker_ids.filter((value) => value !== id) : [...current.worker_ids, id],
    }));
  }

  return (
    <div style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Pay groups</h2>
      <p style={{ marginTop: 0 }}>
        Workers in a group are settled on the same cycle, and its hours are approved together. New workers join the default group.
      </p>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Group</th>
            <th style={styles.th}>Cycle</th>
            <th style={{ ...styles.th, textAlign: "right" }}>Workers</th>
            <th style={styles.th} />
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <tr key={group.id}>
              <td style={styles.td}>
                <strong>{group.name}</strong> {group.is_default && <Badge>Default</Badge>}
              </td>
              <td style={styles.td}>
                {(CYCLES.find(([key]) => key === group.cycle) || [null, group.cycle])[1]}
                {group.cycle === "two_weeks" && group.anchor_date ? `, from ${formatDay(group.anchor_date)}` : ""}
              </td>
              <td style={{ ...styles.td, textAlign: "right" }}>{group.member_count}</td>
              <td style={{ ...styles.td, textAlign: "right", whiteSpace: "nowrap" }}>
                {!group.is_default && (
                  <button type="button" style={styles.quiet} onClick={() => act(() => api(`/pay-groups/${group.id}/make-default/`, { method: "POST" }))}>
                    Make default
                  </button>
                )}{" "}
                {!group.is_default && group.member_count === 0 && (
                  <button type="button" style={styles.danger} onClick={() => act(() => api(`/pay-groups/${group.id}/`, { method: "DELETE" }))}>
                    Delete
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <form onSubmit={add} style={{ ...styles.row, marginTop: "0.8rem" }}>
        <Field label="New group">
          <input style={styles.input} value={form.name} placeholder="e.g. Weekly crew" onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </Field>
        <Field label="Cycle">
          <select style={styles.input} value={form.cycle} onChange={(e) => setForm({ ...form, cycle: e.target.value })}>
            {CYCLES.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        {form.cycle === "two_weeks" && (
          <Field label="A Monday that starts a cycle">
            <input style={styles.input} type="date" value={form.anchor_date} onChange={(e) => setForm({ ...form, anchor_date: e.target.value })} />
          </Field>
        )}
        <button style={styles.button} type="submit">
          Add group
        </button>
      </form>

      <form onSubmit={submitMove} style={{ ...styles.row, marginTop: "0.8rem" }}>
        <Field label="Move into">
          <select style={styles.input} value={move.group} onChange={(e) => setMove({ ...move, group: e.target.value })} required>
            <option value="" disabled>
              Choose
            </option>
            {groups.map((group) => (
              <option key={group.id} value={group.id}>
                {group.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Who">
          <select style={styles.input} value={move.target} onChange={(e) => setMove({ ...move, target: e.target.value })}>
            <option value="workers">Chosen workers</option>
            <option value="team">A team</option>
          </select>
        </Field>
        {move.target === "team" && (
          <Field label="Team">
            <select style={styles.input} value={move.team} onChange={(e) => setMove({ ...move, team: e.target.value })} required>
              <option value="" disabled>
                Choose
              </option>
              {teams.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.number} · {team.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field label="From">
          <input style={styles.input} type="date" value={move.start_date} onChange={(e) => setMove({ ...move, start_date: e.target.value })} required />
        </Field>
        <button style={styles.button} type="submit" disabled={move.target === "workers" && move.worker_ids.length === 0}>
          Move
        </button>
      </form>
      {move.target === "workers" && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem 1.1rem", marginTop: "0.8rem" }}>
          {workers.map((worker) => (
            <label key={worker.id} style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}>
              <input type="checkbox" checked={move.worker_ids.includes(worker.id)} onChange={() => toggleWorker(worker.id)} />
              {worker.name}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function LeaveTypes({ run }) {
  const [types, setTypes] = useState([]);
  const [form, setForm] = useState({ name: "", code: "", paid: true, uses_allowance: false });

  const load = useCallback(async () => {
    setTypes(await apiList("/leave-types/"));
  }, []);

  useEffect(() => {
    load().catch(() => setTypes([]));
  }, [load]);

  async function act(action) {
    if (await run(action)) await load();
  }

  async function add(event) {
    event.preventDefault();
    await act(() => api("/leave-types/", { method: "POST", body: { ...form, position: types.length } }));
    setForm({ name: "", code: "", paid: true, uses_allowance: false });
  }

  return (
    <div style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Kinds of day off</h2>
      <p style={{ marginTop: 0 }}>
        The code shows in the timesheet. Whether a kind is paid, or counts against vacation, can't change once it has been
        used; archive it and add a new one instead.
      </p>
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>Name</th>
            <th style={styles.th}>Code</th>
            <th style={styles.th}>Paid</th>
            <th style={styles.th}>Counts against vacation</th>
            <th style={styles.th} />
          </tr>
        </thead>
        <tbody>
          {types.map((type) => (
            <tr key={type.id} style={{ opacity: type.archived ? 0.55 : 1 }}>
              <td style={styles.td}>{type.name}</td>
              <td style={styles.td}>
                <Badge>{type.code}</Badge>
              </td>
              <td style={styles.td}>{type.paid ? "Paid" : "Unpaid"}</td>
              <td style={styles.td}>{type.uses_allowance ? "Yes" : "No"}</td>
              <td style={{ ...styles.td, textAlign: "right" }}>
                <button
                  type="button"
                  style={styles.quiet}
                  onClick={() => act(() => api(`/leave-types/${type.id}/`, { method: "PATCH", body: { archived: !type.archived } }))}
                >
                  {type.archived ? "Restore" : "Archive"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form onSubmit={add} style={{ ...styles.row, marginTop: "0.8rem" }}>
        <Field label="Name">
          <input style={styles.input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </Field>
        <Field label="Code">
          <input
            style={{ ...styles.input, width: "4rem", minWidth: 0 }}
            maxLength={2}
            value={form.code}
            onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
            required
          />
        </Field>
        <label style={{ display: "flex", gap: "0.35rem", alignItems: "center", paddingBottom: "0.55rem" }}>
          <input type="checkbox" checked={form.paid} onChange={(e) => setForm({ ...form, paid: e.target.checked })} />
          Paid
        </label>
        <label style={{ display: "flex", gap: "0.35rem", alignItems: "center", paddingBottom: "0.55rem" }}>
          <input
            type="checkbox"
            checked={form.uses_allowance}
            onChange={(e) => setForm({ ...form, uses_allowance: e.target.checked })}
          />
          Counts against vacation
        </label>
        <button style={styles.button} type="submit">
          Add kind
        </button>
      </form>
    </div>
  );
}

function DaysOffDefault({ run }) {
  const [value, setValue] = useState("");

  useEffect(() => {
    api("/companies/current/")
      .then((company) => setValue(String(Number(company.leave_days_per_year))))
      .catch(() => {});
  }, []);

  async function save(event) {
    event.preventDefault();
    await run(() => api("/companies/current/", { method: "PATCH", body: { leave_days_per_year: Number(value) } }));
  }

  return (
    <form onSubmit={save} style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Days off per year</h2>
      <p style={{ marginTop: 0 }}>The yearly vacation allowance for workers who don't have their own.</p>
      <div style={styles.row}>
        <Field label="Days">
          <input style={hourInput} type="number" min="0" step="0.5" value={value} onChange={(e) => setValue(e.target.value)} required />
        </Field>
        <button style={styles.button} type="submit">
          Save
        </button>
      </div>
    </form>
  );
}

function WorkTimePage() {
  const { user } = useAuth();
  const { canManage } = useRole();
  const today = companyToday(user?.active_company);
  const [schedules, setSchedules] = useState([]);
  const [teams, setTeams] = useState([]);
  const [workers, setWorkers] = useState([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [scheduleRows, teamRows, workerRows] = await Promise.all([
      apiList("/schedules/"),
      apiList("/teams/"),
      apiList("/workers/"),
    ]);
    setSchedules(scheduleRows);
    setTeams(teamRows);
    setWorkers(workerRows.filter((worker) => worker.status === "active"));
  }, []);

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [load]);

  const run = useCallback(
    async (action) => {
      setError("");
      try {
        await action();
        await load();
        return true;
      } catch (err) {
        setError(err.message);
        return false;
      }
    },
    [load]
  );

  if (!canManage) return <Navigate to="/projects" replace />;

  return (
    <div style={styles.page}>
      <PageHeader title="Work time">Schedules, holidays, pay groups and kinds of day off.</PageHeader>
      <ErrorText>{error}</ErrorText>
      <Schedules schedules={schedules} today={today} run={run} />
      <ApplySchedule schedules={schedules} teams={teams} workers={workers} today={today} run={run} />
      <Holidays today={today} run={run} />
      <PayGroups teams={teams} workers={workers} today={today} run={run} />
      <LeaveTypes run={run} />
      <DaysOffDefault run={run} />
    </div>
  );
}

export default WorkTimePage;
