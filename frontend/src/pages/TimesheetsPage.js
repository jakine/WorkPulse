import { Fragment, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiList } from "../api/client";
import { addDays, isoDate, parseDate, startOfWeek } from "../components/ReportCalendar";
import TimesheetDayPanel from "../components/TimesheetDayPanel";
import { Badge, ErrorText, PageHeader, companyToday, formatDay, styles } from "../components/ui";
import { useAuth, useRole } from "../context/AuthContext";

const LETTERS = ["M", "T", "W", "T", "F", "S", "S"];

const workerColumn = {
  position: "sticky",
  left: 0,
  zIndex: 3,
  background: "var(--surface)",
  borderRight: "1px solid var(--line)",
  borderBottom: "1px solid var(--line)",
  minWidth: "10rem",
  padding: "0.35rem 0.6rem",
  textAlign: "left",
  fontWeight: 600,
};
const dayHead = {
  minWidth: "2.6rem",
  padding: "0.3rem 0",
  textAlign: "center",
  borderBottom: "1px solid var(--line)",
  fontWeight: 600,
  lineHeight: 1.15,
};
const totalHead = { ...dayHead, minWidth: "3.2rem", padding: "0.3rem 0.4rem", color: "var(--muted)", fontSize: "0.72rem" };
const cellBox = { height: "2.3rem", padding: 0, borderBottom: "1px solid var(--line)", textAlign: "center", position: "relative" };
const cellButton = {
  width: "100%",
  height: "100%",
  border: "none",
  background: "transparent",
  color: "inherit",
  font: "inherit",
  cursor: "pointer",
  padding: 0,
};
const hoursInput = {
  width: "2.5rem",
  height: "1.7rem",
  padding: "0 0.15rem",
  textAlign: "center",
  border: "1px solid transparent",
  borderRadius: "var(--radius-sm)",
  background: "transparent",
  color: "var(--ink)",
  font: "inherit",
};

function show(value) {
  const number = Number(value || 0);
  return number ? String(number) : "";
}

function HoursInput({ value, label, missing, extra, onSave }) {
  const [draft, setDraft] = useState(show(value));
  useEffect(() => setDraft(show(value)), [value]);

  function commit() {
    const next = draft.trim();
    if (next === show(value)) return;
    onSave(next);
  }

  return (
    <input
      type="number"
      min="0"
      max="24"
      step="0.25"
      value={draft}
      aria-label={label}
      title={extra ? `${extra} h extra` : missing ? "Nothing recorded" : undefined}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") event.currentTarget.blur();
        if (event.key === "Escape") {
          setDraft(show(value));
          event.currentTarget.blur();
        }
      }}
      style={{
        ...hoursInput,
        borderColor: missing ? "var(--danger)" : "transparent",
        color: extra ? "var(--accent)" : "var(--ink)",
        fontWeight: extra ? 700 : 400,
      }}
    />
  );
}

function OffChip({ off }) {
  const waiting = off.status === "requested";
  return (
    <span
      title={`${off.name}${off.half_day ? " (half day)" : ""}${waiting ? ", waiting for approval" : ""}`}
      style={{
        display: "inline-block",
        minWidth: "1.4rem",
        padding: "0.05rem 0.25rem",
        borderRadius: "999px",
        fontSize: "0.72rem",
        fontWeight: 700,
        color: waiting ? "var(--muted)" : "var(--warn)",
        border: `1px ${waiting ? "dashed" : "solid"} color-mix(in srgb, ${waiting ? "var(--muted)" : "var(--warn)"} 60%, transparent)`,
      }}
    >
      {off.half_day ? "½" : ""}
      {off.code || "Off"}
    </span>
  );
}

function Cell({ row, day, cell, canManage, onSave, onOpen }) {
  const weekend = day.weekday >= 5;
  const background = !cell?.counted && cell
    ? "repeating-linear-gradient(45deg, var(--surface-2), var(--surface-2) 4px, transparent 4px, transparent 8px)"
    : cell?.locked
      ? "color-mix(in srgb, var(--surface-2) 70%, transparent)"
      : day.holiday || weekend
        ? "var(--surface-2)"
        : "transparent";
  const style = {
    ...cellBox,
    background,
    borderLeft: day.weekday === 0 ? "1px solid var(--line)" : "none",
    boxShadow: cell?.flags.includes("worked_on_leave") ? "inset 0 0 0 2px var(--danger)" : "none",
  };
  const label = `${row.name}, ${formatDay(day.date)}`;
  const worked = Number(cell?.worked || 0);

  if (canManage && cell?.editable) {
    return (
      <td style={style}>
        <HoursInput
          value={cell.worked}
          label={`Hours for ${label}`}
          missing={cell.flags.includes("missing")}
          extra={Number(cell.extra) || 0}
          onSave={(value) => onSave(row.worker, day.date, value)}
        />
        {cell.off && (
          <span style={{ position: "absolute", top: 0, right: 1, fontSize: "0.58rem", color: "var(--warn)", fontWeight: 700 }}>
            ½{cell.off.code}
          </span>
        )}
      </td>
    );
  }

  let content = null;
  if (worked) {
    content = (
      <span style={{ color: Number(cell.extra) ? "var(--accent)" : "inherit", fontWeight: Number(cell.extra) ? 700 : 400 }}>
        {worked}
        {cell.entries.length > 1 && <sup style={{ color: "var(--muted)" }}>{cell.entries.length}</sup>}
      </span>
    );
  } else if (cell?.off) {
    content = <OffChip off={cell.off} />;
  } else if (day.holiday && cell) {
    content = <span style={{ color: "var(--muted)", fontSize: "0.75rem", fontWeight: 700 }}>H</span>;
  } else if (cell?.flags.includes("missing")) {
    content = <span aria-label="Nothing recorded" style={{ color: "var(--danger)", fontSize: "1.1rem", lineHeight: 1 }}>•</span>;
  }
  return (
    <td style={style}>
      <button type="button" style={cellButton} aria-label={`Open ${label}`} onClick={() => onOpen(row.worker, day.date)}>
        {content}
      </button>
    </td>
  );
}

function TimesheetsPage() {
  const { user } = useAuth();
  const { canManage } = useRole();
  const today = companyToday(user?.active_company);
  const [groups, setGroups] = useState([]);
  const [teams, setTeams] = useState([]);
  const [group, setGroup] = useState("");
  const [mode, setMode] = useState("period");
  const [anchor, setAnchor] = useState(today);
  const [team, setTeam] = useState("");
  const [sheet, setSheet] = useState(null);
  const [open, setOpen] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([apiList("/pay-groups/"), apiList("/teams/")])
      .then(([groupRows, teamRows]) => {
        setGroups(groupRows);
        setTeams(teamRows);
        setGroup((current) => current || String((groupRows.find((row) => row.is_default) || groupRows[0] || {}).id || ""));
      })
      .catch((err) => setError(err.message));
  }, []);

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (mode === "period") {
      if (!group) return;
      params.set("pay_group", group);
      params.set("date", anchor);
    } else {
      const start = isoDate(startOfWeek(parseDate(anchor)));
      params.set("from", start);
      params.set("to", isoDate(addDays(parseDate(start), 6)));
    }
    if (team) params.set("team", team);
    setSheet(await api(`/timesheets/?${params}`));
  }, [mode, group, anchor, team]);

  useEffect(() => {
    setError("");
    load().catch((err) => setError(err.message));
  }, [load]);

  const reload = useCallback(() => {
    load().catch((err) => setError(err.message));
  }, [load]);

  function shift(direction) {
    if (!sheet) return;
    setAnchor(isoDate(addDays(parseDate(direction < 0 ? sheet.start : sheet.end), direction)));
  }

  async function saveCell(worker, date, value) {
    setError("");
    try {
      await api("/timesheets/cell/", { method: "PUT", body: { worker, date, hours: value === "" ? 0 : Number(value) } });
      await load();
    } catch (err) {
      setError(err.message);
      if (/day panel|other work/i.test(err.message)) setOpen({ worker, date });
    }
  }

  async function run(action) {
    setError("");
    try {
      await action();
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  function approve() {
    const missing = sheet.workers.reduce((sum, row) => sum + row.totals.missing, 0);
    const conflicts = sheet.workers.reduce((sum, row) => sum + row.totals.worked_on_leave, 0);
    const warnings = [
      missing && `${missing} scheduled day${missing === 1 ? " has" : "s have"} no hours`,
      conflicts && `${conflicts} day${conflicts === 1 ? " was" : "s were"} worked during a day off`,
    ].filter(Boolean);
    const question = `${warnings.length ? `${warnings.join(" and ")}. ` : ""}Approve ${sheet.pay_group.name}, ${sheet.period.label}? Hours, days off and schedules in it will be locked.`;
    if (!window.confirm(question)) return;
    run(() =>
      api("/timesheet-periods/approve/", {
        method: "POST",
        body: { pay_group: Number(group), start_date: sheet.start, end_date: sheet.end },
      })
    );
  }

  function reopen() {
    if (!window.confirm(`Reopen ${sheet.pay_group.name}, ${sheet.period.label}? Its hours can be changed again.`)) return;
    run(() => api(`/timesheet-periods/${sheet.period.id}/reopen/`, { method: "POST" }));
  }

  const period = mode === "period" ? sheet?.period : null;
  const approved = period?.status === "approved";
  let lastTeam = null;

  return (
    <div style={styles.page}>
      <PageHeader title="Timesheet">
        Hours per worker per day. Type hours into a cell, or open a day for projects, other work and days off.
      </PageHeader>
      <ErrorText>{error}</ErrorText>

      <div style={{ ...styles.card, display: "flex", gap: "0.6rem", flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ display: "flex", gap: "0.3rem" }}>
          <button type="button" className={`ghost-btn${mode === "period" ? " is-on" : ""}`} onClick={() => setMode("period")}>
            Pay period
          </button>
          <button type="button" className={`ghost-btn${mode === "week" ? " is-on" : ""}`} onClick={() => setMode("week")}>
            Week
          </button>
        </div>
        {mode === "period" && (
          <select style={{ ...styles.input, width: "auto" }} value={group} onChange={(e) => setGroup(e.target.value)} aria-label="Pay group">
            {groups.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
        )}
        <select style={{ ...styles.input, width: "auto" }} value={team} onChange={(e) => setTeam(e.target.value)} aria-label="Team">
          <option value="">All teams</option>
          {teams.map((row) => (
            <option key={row.id} value={row.id}>
              {row.number} · {row.name}
            </option>
          ))}
        </select>
        <button type="button" style={styles.quiet} onClick={() => shift(-1)}>
          ← Earlier
        </button>
        <button type="button" style={styles.quiet} onClick={() => setAnchor(today)}>
          {mode === "period" ? "This period" : "This week"}
        </button>
        <button type="button" style={styles.quiet} onClick={() => shift(1)}>
          Later →
        </button>
        {sheet && (
          <strong>
            {formatDay(sheet.start)} – {formatDay(sheet.end)}
          </strong>
        )}
        {period && (
          <>
            <Badge color={approved ? "var(--accent)" : "var(--muted)"}>{approved ? "Approved" : "Open"}</Badge>
            {approved && period.approved_by_email && (
              <span style={{ color: "var(--muted)", fontSize: "0.85rem" }}>by {period.approved_by_email}</span>
            )}
            {canManage && !approved && period.over && (
              <button type="button" style={styles.button} onClick={approve}>
                Approve hours
              </button>
            )}
            {canManage && approved && (
              <button type="button" style={styles.quiet} onClick={reopen}>
                Reopen
              </button>
            )}
          </>
        )}
      </div>

      {sheet && (
        <div style={{ overflowX: "auto", border: "1px solid var(--line)", borderRadius: "var(--radius)", background: "var(--surface)" }}>
          <table style={{ borderCollapse: "separate", borderSpacing: 0, fontSize: "0.82rem", minWidth: "100%" }}>
            <thead>
              <tr>
                <th style={{ ...workerColumn, zIndex: 4 }}>Worker</th>
                {sheet.days.map((day) => {
                  const isToday = day.date === sheet.today;
                  return (
                    <th
                      key={day.date}
                      title={day.holiday || undefined}
                      style={{
                        ...dayHead,
                        background: day.holiday || day.weekday >= 5 ? "var(--surface-2)" : "transparent",
                        color: isToday ? "var(--accent)" : day.holiday ? "var(--warn)" : "inherit",
                        fontWeight: isToday ? 750 : 600,
                        borderLeft: day.weekday === 0 ? "1px solid var(--line)" : "none",
                      }}
                    >
                      <div style={{ fontSize: "0.68rem", color: isToday ? "var(--accent)" : "var(--muted)" }}>{LETTERS[day.weekday]}</div>
                      {Number(day.date.slice(8))}
                    </th>
                  );
                })}
                {["Days", "Hours", "Extra", "Off", "Missing"].map((label) => (
                  <th key={label} style={{ ...totalHead, borderLeft: label === "Days" ? "1px solid var(--line)" : "none" }}>
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sheet.workers.map((row) => {
                const header = row.team_name !== lastTeam;
                lastTeam = row.team_name;
                const offTotal = Number(row.totals.paid_off) + Number(row.totals.unpaid_off);
                return (
                  <Fragment key={row.worker}>
                    {header && (
                      <tr>
                        <th
                          colSpan={sheet.days.length + 6}
                          style={{
                            textAlign: "left",
                            padding: "0.45rem 0.6rem",
                            background: "var(--surface-2)",
                            color: "var(--muted)",
                            fontSize: "0.72rem",
                            textTransform: "uppercase",
                            letterSpacing: "0.04em",
                          }}
                        >
                          {row.team_name ? `${row.team_number} · ${row.team_name}` : "No team"}
                        </th>
                      </tr>
                    )}
                    <tr>
                      <th scope="row" style={workerColumn}>
                        <Link to={`/workers/${row.worker}?tab=time`}>{row.name}</Link>
                      </th>
                      {sheet.days.map((day) => (
                        <Cell
                          key={day.date}
                          row={row}
                          day={day}
                          cell={row.cells[day.date]}
                          canManage={canManage}
                          onSave={saveCell}
                          onOpen={(worker, date) => setOpen({ worker, date })}
                        />
                      ))}
                      <td style={{ ...cellBox, borderLeft: "1px solid var(--line)", fontWeight: 650 }}>{Number(row.totals.days)}</td>
                      <td style={cellBox}>{Number(row.totals.hours)}</td>
                      <td style={{ ...cellBox, color: Number(row.totals.extra) ? "var(--accent)" : "var(--muted)" }}>
                        {Number(row.totals.extra) || "–"}
                      </td>
                      <td
                        style={{ ...cellBox, color: offTotal ? "var(--warn)" : "var(--muted)" }}
                        title={Object.entries(row.totals.off).map(([code, days]) => `${code} ${Number(days)}`).join(" · ")}
                      >
                        {offTotal || "–"}
                      </td>
                      <td style={{ ...cellBox, color: row.totals.missing ? "var(--danger)" : "var(--muted)" }}>{row.totals.missing || "–"}</td>
                    </tr>
                  </Fragment>
                );
              })}
            </tbody>
            {sheet.workers.length > 0 && (
              <tfoot>
                <tr>
                  <th style={{ ...workerColumn, color: "var(--muted)", fontWeight: 600 }}>Hours / people</th>
                  {sheet.days.map((day) => {
                    const total = sheet.daily[day.date];
                    return (
                      <td
                        key={day.date}
                        style={{ ...cellBox, fontSize: "0.7rem", color: "var(--muted)", lineHeight: 1.15, borderLeft: day.weekday === 0 ? "1px solid var(--line)" : "none" }}
                      >
                        {total ? (
                          <>
                            {Number(total.hours)}
                            <br />
                            {total.people}
                          </>
                        ) : null}
                      </td>
                    );
                  })}
                  <td colSpan={5} style={{ ...cellBox, borderLeft: "1px solid var(--line)" }} />
                </tr>
              </tfoot>
            )}
          </table>
          {sheet.workers.length === 0 && <p style={{ padding: "1rem", margin: 0 }}>Nobody to show for these dates.</p>}
        </div>
      )}

      <p style={{ color: "var(--muted)", fontSize: "0.82rem", margin: 0 }}>
        Blue hours go past the schedule. V, S, U… are days off (dashed while waiting), H is a holiday, a red dot is a scheduled day with
        nothing recorded. Striped days belong to another pay group.
      </p>

      {open && (
        <TimesheetDayPanel
          workerId={open.worker}
          date={open.date}
          canManage={canManage}
          onClose={() => setOpen(null)}
          onChanged={reload}
        />
      )}
    </div>
  );
}

export default TimesheetsPage;
