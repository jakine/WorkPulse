import { useCallback, useEffect, useState } from "react";
import { api, apiList } from "../api/client";
import { addDays, formatLongDay, isoDate, parseDate, startOfWeek } from "./ReportCalendar";
import { Badge, ErrorText, Field, styles } from "./ui";

const panelStyle = {
  position: "fixed",
  top: 0,
  right: 0,
  bottom: 0,
  width: "min(460px, 100vw)",
  background: "var(--surface)",
  borderLeft: "1px solid var(--line)",
  boxShadow: "var(--shadow)",
  padding: "1.25rem",
  overflowY: "auto",
  zIndex: 20,
  display: "grid",
  gap: "1rem",
  alignContent: "start",
};

const small = { ...styles.input, width: "5rem", minWidth: 0 };
const section = { display: "grid", gap: "0.5rem" };

function hours(value) {
  return `${Number(value)} h`;
}

function SiteRow({ entry, editable, onSave }) {
  const [draft, setDraft] = useState(String(Number(entry.hours)));
  useEffect(() => setDraft(String(Number(entry.hours))), [entry.hours]);
  return (
    <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
      <strong style={{ flex: "1 1 8rem" }}>{entry.project_name || "Project"}</strong>
      {editable ? (
        <>
          <input
            style={small}
            type="number"
            min="0.25"
            max="24"
            step="0.25"
            value={draft}
            aria-label={`Hours on ${entry.project_name}`}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button type="button" style={styles.quiet} onClick={() => onSave(entry.workplace, draft)} disabled={Number(draft) === Number(entry.hours)}>
            Save
          </button>
          <button type="button" style={styles.danger} onClick={() => onSave(entry.workplace, "0")}>
            Remove
          </button>
        </>
      ) : (
        <span>
          {hours(entry.hours)} {entry.day_approved && <Badge color="var(--muted)">Day approved</Badge>}
        </span>
      )}
    </div>
  );
}

function TimesheetDayPanel({ workerId, date, canManage, onClose, onChanged }) {
  const [day, setDay] = useState(null);
  const [types, setTypes] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [site, setSite] = useState({ workplace: "", hours: "8" });
  const [other, setOther] = useState({ kind: "yard", hours: "8", note: "" });
  const [off, setOff] = useState({ leave_type: "", half_day: false });

  const load = useCallback(async () => {
    const [detail, typeRows] = await Promise.all([
      api(`/timesheets/day/?worker=${workerId}&date=${date}`),
      apiList("/leave-types/"),
    ]);
    setDay(detail);
    setTypes(typeRows.filter((type) => !type.archived));
    const expected = Number(detail.cell.expected) || 8;
    setSite((current) => ({ ...current, hours: String(expected) }));
  }, [workerId, date]);

  useEffect(() => {
    setError("");
    setNotice("");
    load().catch((err) => setError(err.message));
  }, [load]);

  async function run(action, message = "") {
    setError("");
    setNotice("");
    try {
      const result = await action();
      await load();
      onChanged();
      if (message) setNotice(typeof message === "function" ? message(result) : message);
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    }
  }

  function saveSite(workplace, value) {
    return run(() =>
      api("/timesheets/cell/", {
        method: "PUT",
        body: { worker: workerId, date, hours: Number(value || 0), workplace: Number(workplace) },
      })
    );
  }

  async function addOther(event) {
    event.preventDefault();
    const ok = await run(() =>
      api("/other-work/", { method: "POST", body: { worker: workerId, work_date: date, ...other, hours: Number(other.hours) } })
    );
    if (ok) setOther({ kind: "yard", hours: "8", note: "" });
  }

  async function addOff(event) {
    event.preventDefault();
    await run(() =>
      api("/days-off/", {
        method: "POST",
        body: { worker: workerId, leave_type: Number(off.leave_type), start_date: date, end_date: date, half_day: off.half_day },
      })
    );
  }

  function fillWeek() {
    const start = isoDate(startOfWeek(parseDate(date)));
    const end = isoDate(addDays(parseDate(start), 6));
    return run(
      () => api("/timesheets/fill/", { method: "POST", body: { worker: workerId, from: start, to: end } }),
      (result) =>
        `Filled ${result.filled} day${result.filled === 1 ? "" : "s"}.` +
        (result.skipped.length ? ` Skipped: ${result.skipped.map((row) => `${row.date} (${row.reason})`).join("; ")}` : "")
    );
  }

  const cell = day?.cell;
  const writable = canManage && cell && !cell.locked && cell.counted;
  const siteEntries = cell ? cell.entries.filter((entry) => entry.type === "site") : [];
  const otherEntries = cell ? cell.entries.filter((entry) => entry.type === "other") : [];
  const freePlacements = day ? day.placements.filter((place) => !siteEntries.some((entry) => entry.workplace === place.workplace)) : [];

  return (
    <aside style={panelStyle} aria-label="Day details">
      <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "start" }}>
        <div>
          <h2 style={{ margin: 0 }}>{day?.name || "…"}</h2>
          <div style={{ color: "var(--muted)" }}>{formatLongDay(date)}</div>
        </div>
        <button type="button" style={styles.quiet} onClick={onClose}>
          Close
        </button>
      </div>
      <ErrorText>{error}</ErrorText>
      {notice && <p style={{ margin: 0 }}>{notice}</p>}
      {cell && (
        <>
          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
            <span>Expected {hours(cell.expected)}</span>
            <span>· Worked {hours(cell.worked)}</span>
            {Number(cell.extra) > 0 && <Badge>+{Number(cell.extra)} h extra</Badge>}
            {day.holiday && <Badge color="var(--muted)">{day.holiday}</Badge>}
            {cell.off && (
              <Badge color={cell.off.status === "approved" ? "var(--warn)" : "var(--muted)"}>
                {cell.off.name}
                {cell.off.half_day ? " (half day)" : ""}
                {cell.off.status === "requested" ? " · waiting" : ""}
              </Badge>
            )}
            {cell.flags.includes("worked_on_leave") && <Badge color="var(--danger)">Worked during a day off</Badge>}
          </div>
          {cell.locked && <p style={{ margin: 0, color: "var(--muted)" }}>This day is in an approved period. Reopen the period to change it.</p>}

          <div style={section}>
            <h3 style={{ margin: 0 }}>On projects</h3>
            {siteEntries.length === 0 && <p style={{ margin: 0, color: "var(--muted)" }}>No project hours.</p>}
            {siteEntries.map((entry) => (
              <SiteRow key={entry.id} entry={entry} editable={writable && !entry.day_approved} onSave={saveSite} />
            ))}
            {writable && freePlacements.length > 0 && (
              <div style={styles.row}>
                <Field label="Add to project">
                  <select style={styles.input} value={site.workplace} onChange={(e) => setSite({ ...site, workplace: e.target.value })}>
                    <option value="">Choose</option>
                    {freePlacements.map((place) => (
                      <option key={place.workplace} value={place.workplace}>
                        {place.name} ({place.team_name})
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Hours">
                  <input
                    style={small}
                    type="number"
                    min="0.25"
                    max="24"
                    step="0.25"
                    value={site.hours}
                    onChange={(e) => setSite({ ...site, hours: e.target.value })}
                  />
                </Field>
                <button type="button" style={styles.button} disabled={!site.workplace} onClick={() => saveSite(site.workplace, site.hours)}>
                  Add
                </button>
              </div>
            )}
            {writable && day.placements.length === 0 && siteEntries.length === 0 && (
              <p style={{ margin: 0, color: "var(--muted)" }}>Their team wasn't placed on a project that day.</p>
            )}
          </div>

          <div style={section}>
            <h3 style={{ margin: 0 }}>Other work</h3>
            {otherEntries.length === 0 && <p style={{ margin: 0, color: "var(--muted)" }}>Nothing away from projects.</p>}
            {otherEntries.map((entry) => (
              <div key={entry.id} style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                <strong style={{ flex: 1 }}>
                  {(day.other_kinds.find(([key]) => key === entry.kind) || [entry.kind, entry.kind])[1]} · {hours(entry.hours)}
                  {entry.note && <span style={{ color: "var(--muted)", fontWeight: 400 }}> · {entry.note}</span>}
                </strong>
                {writable && (
                  <button type="button" style={styles.danger} onClick={() => run(() => api(`/other-work/${entry.id}/`, { method: "DELETE" }))}>
                    Remove
                  </button>
                )}
              </div>
            ))}
            {writable && (
              <form onSubmit={addOther} style={styles.row}>
                <Field label="Kind">
                  <select style={styles.input} value={other.kind} onChange={(e) => setOther({ ...other, kind: e.target.value })}>
                    {day.other_kinds.map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Hours">
                  <input
                    style={small}
                    type="number"
                    min="0.25"
                    max="24"
                    step="0.25"
                    value={other.hours}
                    onChange={(e) => setOther({ ...other, hours: e.target.value })}
                    required
                  />
                </Field>
                <Field label="Note">
                  <input style={styles.input} value={other.note} onChange={(e) => setOther({ ...other, note: e.target.value })} />
                </Field>
                <button style={styles.button} type="submit">
                  Add
                </button>
              </form>
            )}
          </div>

          {writable && !cell.off && (
            <form onSubmit={addOff} style={section}>
              <h3 style={{ margin: 0 }}>Day off</h3>
              <div style={styles.row}>
                <Field label="Kind">
                  <select style={styles.input} value={off.leave_type} onChange={(e) => setOff({ ...off, leave_type: e.target.value })} required>
                    <option value="" disabled>
                      Choose
                    </option>
                    {types.map((type) => (
                      <option key={type.id} value={type.id}>
                        {type.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <label style={{ display: "flex", gap: "0.35rem", alignItems: "center", paddingBottom: "0.55rem" }}>
                  <input type="checkbox" checked={off.half_day} onChange={(e) => setOff({ ...off, half_day: e.target.checked })} />
                  Half day
                </label>
                <button style={styles.button} type="submit">
                  Add day off
                </button>
              </div>
            </form>
          )}

          {canManage && (
            <div>
              <button type="button" style={styles.quiet} onClick={fillWeek}>
                Fill this week from the schedule
              </button>
              <p style={{ color: "var(--muted)", fontSize: "0.82rem", marginBottom: 0 }}>
                Records scheduled hours on the team's project for past days that have nothing yet. Days off and holidays are skipped.
              </p>
            </div>
          )}
        </>
      )}
    </aside>
  );
}

export default TimesheetDayPanel;
