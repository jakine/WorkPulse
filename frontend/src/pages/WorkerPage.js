import { useCallback, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, apiList } from "../api/client";
import { BalanceTiles, DayOffForm, DayOffList } from "../components/DaysOff";
import WorkerPay from "../components/WorkerPay";
import { addDays, isoDate, parseDate, startOfWeek } from "../components/ReportCalendar";
import { WeeklyColumns } from "../components/charts";
import { Badge, ErrorText, Field, PageHeader, Tabs, companyToday, formatDay, styles } from "../components/ui";
import { WEEKDAYS, hoursLabel } from "../components/hours";
import { useAuth, useRole } from "../context/AuthContext";

function detailsForm(worker) {
  return {
    name: worker.name,
    contact: worker.contact || "",
    worker_type: worker.worker_type ? String(worker.worker_type) : "",
    status: worker.status,
    hired_on: worker.hired_on || "",
    left_on: worker.left_on || "",
    leave_allowance: worker.leave_allowance ?? "",
  };
}

function EmploymentDetails({ worker, onSaved, onError }) {
  const [types, setTypes] = useState([]);
  const [form, setForm] = useState(null);

  useEffect(() => {
    apiList("/worker-types/").then(setTypes).catch(() => setTypes([]));
  }, []);

  async function save(event) {
    event.preventDefault();
    onError("");
    try {
      const saved = await api(`/workers/${worker.id}/`, {
        method: "PATCH",
        body: {
          name: form.name,
          contact: form.contact,
          worker_type: form.worker_type ? Number(form.worker_type) : null,
          status: form.status,
          hired_on: form.hired_on || null,
          left_on: form.left_on || null,
          leave_allowance: form.leave_allowance === "" ? null : Number(form.leave_allowance),
        },
      });
      setForm(null);
      onSaved(saved);
    } catch (err) {
      onError(err.message);
    }
  }

  if (!form) {
    return (
      <div>
        <button type="button" style={styles.quiet} onClick={() => setForm(detailsForm(worker))}>
          Edit details
        </button>
      </div>
    );
  }

  const set = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  return (
    <form onSubmit={save} style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Edit details</h2>
      <div style={styles.row}>
        <Field label="Name">
          <input style={styles.input} value={form.name} onChange={(e) => set("name", e.target.value)} required />
        </Field>
        <Field label="Contact">
          <input style={styles.input} value={form.contact} onChange={(e) => set("contact", e.target.value)} />
        </Field>
        <Field label="Type">
          <select style={styles.input} value={form.worker_type} onChange={(e) => set("worker_type", e.target.value)}>
            <option value="">None</option>
            {types.map((type) => (
              <option key={type.id} value={type.id}>
                {type.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Status">
          <select style={styles.input} value={form.status} onChange={(e) => set("status", e.target.value)}>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
          </select>
        </Field>
      </div>
      <div style={{ ...styles.row, marginTop: "0.8rem" }}>
        <Field label="First working day">
          <input style={styles.input} type="date" value={form.hired_on} onChange={(e) => set("hired_on", e.target.value)} />
        </Field>
        <Field label="Last working day">
          <input style={styles.input} type="date" value={form.left_on} onChange={(e) => set("left_on", e.target.value)} />
        </Field>
        <Field label="Days off per year">
          <input
            style={styles.input}
            type="number"
            min="0"
            step="0.5"
            placeholder="Company default"
            value={form.leave_allowance}
            onChange={(e) => set("leave_allowance", e.target.value)}
          />
        </Field>
        <button style={styles.button} type="submit">
          Save
        </button>
        <button style={styles.quiet} type="button" onClick={() => setForm(null)}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function WorkerSchedule({ worker, today, canManage, onChanged, onError }) {
  const [schedules, setSchedules] = useState([]);
  const [history, setHistory] = useState([]);
  const [change, setChange] = useState({ schedule: "", start_date: today });

  const load = useCallback(async () => {
    const [scheduleRows, rows] = await Promise.all([
      apiList("/schedules/"),
      apiList(`/schedule-assignments/?worker=${worker.id}`),
    ]);
    setSchedules(scheduleRows);
    setHistory(rows.filter((row) => row.worker === worker.id));
  }, [worker.id]);

  useEffect(() => {
    load().catch(() => setHistory([]));
  }, [load]);

  async function submit(event) {
    event.preventDefault();
    onError("");
    const body = { worker_ids: [worker.id], start_date: change.start_date };
    const path = change.schedule === "default" ? "/schedules/reset/" : `/schedules/${change.schedule}/apply/`;
    try {
      await api(path, { method: "POST", body });
      setChange({ schedule: "", start_date: today });
      await load();
      onChanged();
    } catch (err) {
      onError(err.message);
    }
  }

  const current = worker.schedule;
  return (
    <div style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Schedule</h2>
      {current ? (
        <>
          <p style={{ marginTop: 0 }}>
            <strong>{current.name}</strong> {current.own ? <Badge>Own schedule</Badge> : <Badge color="var(--muted)">Company default</Badge>}
          </p>
          <table style={{ ...styles.table, width: "auto" }}>
            <thead>
              <tr>
                {WEEKDAYS.map(([key, label]) => (
                  <th key={key} style={{ ...styles.th, textAlign: "right" }}>
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                {WEEKDAYS.map(([key]) => (
                  <td key={key} style={{ ...styles.td, textAlign: "right", minWidth: "2.6rem" }}>
                    {hoursLabel(current.hours[key])}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </>
      ) : (
        <p style={{ marginTop: 0 }}>No schedule yet.</p>
      )}
      {history.length > 0 && (
        <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
          Own schedules:{" "}
          {history
            .map(
              (row) =>
                `${row.schedule_name} ${row.start_date ? `from ${formatDay(row.start_date)}` : ""}${row.end_date ? ` to ${formatDay(row.end_date)}` : ""}`
            )
            .join(" · ")}
          . Other days follow the company default.
        </p>
      )}
      {canManage && (
        <form onSubmit={submit} style={{ ...styles.row, marginTop: "0.8rem" }}>
          <Field label="Change schedule to">
            <select
              style={styles.input}
              value={change.schedule}
              onChange={(e) => setChange({ ...change, schedule: e.target.value })}
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
              <option value="default">Company default</option>
            </select>
          </Field>
          <Field label="From">
            <input
              style={styles.input}
              type="date"
              value={change.start_date}
              onChange={(e) => setChange({ ...change, start_date: e.target.value })}
              required
            />
          </Field>
          <button style={styles.button} type="submit">
            Change
          </button>
        </form>
      )}
    </div>
  );
}

const TABS = [
  ["overview", "Overview"],
  ["time", "Time"],
  ["days-off", "Days off"],
];

const CYCLES = { weekly: "weekly", two_weeks: "every two weeks", monthly: "monthly" };

function WorkerTime({ worker, today, canManage, onError, onChanged }) {
  const monthStart = `${today.slice(0, 8)}01`;
  const [month, setMonth] = useState(null);
  const [weeks, setWeeks] = useState([]);
  const [groups, setGroups] = useState([]);
  const [move, setMove] = useState({ group: "", start_date: today });

  const load = useCallback(async () => {
    const since = isoDate(addDays(startOfWeek(parseDate(today)), -49));
    const [monthSheet, weekSheet, groupRows] = await Promise.all([
      api(`/timesheets/?worker=${worker.id}&from=${monthStart}&to=${today}`),
      api(`/timesheets/?worker=${worker.id}&from=${since}&to=${today}`),
      apiList("/pay-groups/"),
    ]);
    setMonth(monthSheet.workers[0] || null);
    setWeeks((weekSheet.workers[0]?.weeks || []).map((row) => ({ week: row.week, quantity: row.hours })));
    setGroups(groupRows);
  }, [worker.id, monthStart, today]);

  useEffect(() => {
    load().catch((err) => onError(err.message));
  }, [load, onError]);

  async function submitMove(event) {
    event.preventDefault();
    onError("");
    try {
      await api(`/pay-groups/${move.group}/assign/`, {
        method: "POST",
        body: { worker_ids: [worker.id], start_date: move.start_date },
      });
      setMove({ group: "", start_date: today });
      onChanged();
    } catch (err) {
      onError(err.message);
    }
  }

  const totals = month?.totals;
  const tiles = totals
    ? [
        ["Days worked", totals.days],
        ["Hours", totals.hours],
        ["Extra hours", totals.extra],
        ["Days off", Number(totals.paid_off) + Number(totals.unpaid_off)],
        ["Days with nothing recorded", totals.missing],
      ]
    : [];
  return (
    <>
      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>This month so far</h2>
        {totals ? (
          <div style={styles.stats}>
            {tiles.map(([label, value]) => (
              <div key={label} style={styles.stat}>
                <div style={styles.label}>{label}</div>
                <strong>{Number(value)}</strong>
              </div>
            ))}
          </div>
        ) : (
          <p>Not employed this month.</p>
        )}
        <p style={{ marginBottom: 0 }}>
          <Link to="/timesheets">Open the timesheet</Link>
        </p>
      </div>
      {weeks.length > 0 && <WeeklyColumns title="Hours per week" unit="h" weeks={weeks} />}
      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Pay group</h2>
        <p style={{ marginTop: 0 }}>
          {worker.pay_group ? (
            <>
              <strong>{worker.pay_group.name}</strong>, settled {CYCLES[worker.pay_group.cycle]}
              {worker.pay_group.since ? ` since ${formatDay(worker.pay_group.since)}` : ""}.
            </>
          ) : (
            "Not in a pay group."
          )}
        </p>
        {canManage && (
          <form onSubmit={submitMove} style={styles.row}>
            <Field label="Move to">
              <select style={styles.input} value={move.group} onChange={(e) => setMove({ ...move, group: e.target.value })} required>
                <option value="" disabled>
                  Choose
                </option>
                {groups
                  .filter((group) => group.id !== worker.pay_group?.id)
                  .map((group) => (
                    <option key={group.id} value={group.id}>
                      {group.name}
                    </option>
                  ))}
              </select>
            </Field>
            <Field label="From">
              <input
                style={styles.input}
                type="date"
                value={move.start_date}
                onChange={(e) => setMove({ ...move, start_date: e.target.value })}
                required
              />
            </Field>
            <button style={styles.button} type="submit">
              Move
            </button>
          </form>
        )}
      </div>
    </>
  );
}

function WorkerDaysOff({ worker, today, canManage, canAsk, userId, onError }) {
  const year = Number(today.slice(0, 4));
  const [types, setTypes] = useState([]);
  const [rows, setRows] = useState([]);
  const [balance, setBalance] = useState(null);

  const load = useCallback(async () => {
    const [typeRows, leaveRows, balanceRows] = await Promise.all([
      apiList("/leave-types/"),
      apiList(`/days-off/?worker=${worker.id}`),
      apiList(`/days-off/balances/?year=${year}&worker=${worker.id}`),
    ]);
    setTypes(typeRows);
    setRows(leaveRows);
    setBalance(balanceRows[0] || null);
  }, [worker.id, year]);

  useEffect(() => {
    load().catch((err) => onError(err.message));
  }, [load, onError]);

  async function act(row, action) {
    onError("");
    try {
      await api(`/days-off/${row.id}/${action}/`, { method: "POST" });
      await load();
    } catch (err) {
      onError(err.message);
    }
  }

  return (
    <>
      <BalanceTiles balance={balance} />
      {canAsk && (
        <DayOffForm
          workers={[]}
          fixedWorker={worker.id}
          types={types}
          canManage={canManage}
          today={today}
          onSaved={() => load().catch((err) => onError(err.message))}
          onError={onError}
        />
      )}
      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Days off</h2>
        <DayOffList rows={rows} showWorker={false} canManage={canManage} userId={userId} onAction={act} />
      </div>
    </>
  );
}

function WorkerPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const { canManage, isOwner } = useRole();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabs = isOwner ? [...TABS, ["pay", "Pay"]] : TABS;
  const requestedTab = searchParams.get("tab") || "overview";
  const tab = tabs.some(([key]) => key === requestedTab) ? requestedTab : "overview";
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

  function reload() {
    load().catch((err) => setError(err.message));
  }

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
      {worker && <Tabs tabs={tabs} value={tab} onChange={(key) => setSearchParams({ tab: key })} />}
      {worker && tab === "pay" && <WorkerPay worker={worker} today={today} onError={setError} />}
      {worker && tab === "time" && (
        <WorkerTime worker={worker} today={today} canManage={canManage} onError={setError} onChanged={reload} />
      )}
      {worker && tab === "days-off" && (
        <WorkerDaysOff
          worker={worker}
          today={today}
          canManage={canManage}
          canAsk={canManage || teams.some((team) => team.id === worker.team && team.lead_user === user?.id)}
          userId={user?.id}
          onError={setError}
        />
      )}
      {worker && tab === "overview" && (
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
            <div style={styles.stat}>
              <div style={styles.label}>Employed</div>
              <strong>
                {worker.hired_on ? `Since ${formatDay(worker.hired_on)}` : "Before records"}
                {worker.left_on ? `, until ${formatDay(worker.left_on)}` : ""}
              </strong>
            </div>
          </div>

          {canManage && <EmploymentDetails worker={worker} onSaved={reload} onError={setError} />}

          <WorkerSchedule worker={worker} today={today} canManage={canManage} onChanged={reload} onError={setError} />

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
