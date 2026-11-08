import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Badge, Field, formatDay, styles } from "./ui";

const STATUS = {
  requested: ["Waiting", "var(--warn)"],
  approved: ["Approved", "var(--accent)"],
  rejected: ["Rejected", "var(--muted)"],
  cancelled: ["Cancelled", "var(--muted)"],
};

export function dayRange(row) {
  if (row.start_date === row.end_date) return `${formatDay(row.start_date)}${row.half_day ? " (half day)" : ""}`;
  return `${formatDay(row.start_date)} – ${formatDay(row.end_date)}`;
}

function daysLabel(value) {
  const number = Number(value);
  return `${number} working day${number === 1 ? "" : "s"}`;
}

export function DayOffForm({ workers, types, fixedWorker, canManage, today, onSaved, onError }) {
  const empty = { worker: fixedWorker ? String(fixedWorker) : "", leave_type: "", start_date: today, end_date: today, half_day: false, note: "" };
  const [form, setForm] = useState(empty);
  const [preview, setPreview] = useState(null);
  const usable = types.filter((type) => !type.archived);

  useEffect(() => {
    if (!form.worker || !form.start_date || !form.end_date || form.end_date < form.start_date) {
      setPreview(null);
      return undefined;
    }
    const params = new URLSearchParams({
      worker: form.worker,
      start_date: form.start_date,
      end_date: form.end_date,
      half_day: form.half_day && form.start_date === form.end_date ? "true" : "false",
    });
    if (form.leave_type) params.set("leave_type", form.leave_type);
    const timer = setTimeout(() => {
      api(`/days-off/preview/?${params}`)
        .then(setPreview)
        .catch(() => setPreview(null));
    }, 250);
    return () => clearTimeout(timer);
  }, [form.worker, form.leave_type, form.start_date, form.end_date, form.half_day]);

  function set(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    onError("");
    try {
      await api("/days-off/", {
        method: "POST",
        body: {
          worker: Number(form.worker),
          leave_type: Number(form.leave_type),
          start_date: form.start_date,
          end_date: form.end_date,
          half_day: form.half_day && form.start_date === form.end_date,
          note: form.note,
        },
      });
      setForm(empty);
      onSaved();
    } catch (err) {
      onError(err.message);
    }
  }

  return (
    <form onSubmit={submit} style={styles.card}>
      <h2 style={{ marginTop: 0 }}>{canManage ? "Add a day off" : "Ask for a day off"}</h2>
      <div style={styles.row}>
        {!fixedWorker && (
          <Field label="Worker">
            <select style={styles.input} value={form.worker} onChange={(e) => set("worker", e.target.value)} required>
              <option value="" disabled>
                Choose
              </option>
              {workers.map((worker) => (
                <option key={worker.id} value={worker.id}>
                  {worker.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field label="Type">
          <select style={styles.input} value={form.leave_type} onChange={(e) => set("leave_type", e.target.value)} required>
            <option value="" disabled>
              Choose
            </option>
            {usable.map((type) => (
              <option key={type.id} value={type.id}>
                {type.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="From">
          <input
            style={styles.input}
            type="date"
            value={form.start_date}
            onChange={(e) => setForm((current) => ({ ...current, start_date: e.target.value, end_date: current.end_date < e.target.value ? e.target.value : current.end_date }))}
            required
          />
        </Field>
        <Field label="To">
          <input
            style={styles.input}
            type="date"
            min={form.start_date}
            value={form.end_date}
            onChange={(e) => set("end_date", e.target.value)}
            required
          />
        </Field>
        {form.start_date === form.end_date && (
          <label style={{ display: "flex", gap: "0.35rem", alignItems: "center", paddingBottom: "0.55rem" }}>
            <input type="checkbox" checked={form.half_day} onChange={(e) => set("half_day", e.target.checked)} />
            Half day
          </label>
        )}
        <Field label="Note">
          <input style={styles.input} value={form.note} onChange={(e) => set("note", e.target.value)} maxLength={300} />
        </Field>
        <button style={styles.button} type="submit">
          {canManage ? "Add" : "Ask"}
        </button>
      </div>
      {preview && (
        <p style={{ marginBottom: 0 }}>
          {daysLabel(preview.days)}
          {preview.holidays.length > 0 && ` · skips ${preview.holidays.map((day) => day.name).join(", ")}`}
          {preview.left_after != null && ` · ${Number(preview.left_after)} vacation days left after this`}
        </p>
      )}
    </form>
  );
}

export function DayOffList({ rows, canManage, userId, showWorker = true, onAction, empty = "No days off." }) {
  if (rows.length === 0) return <p style={{ color: "var(--muted)" }}>{empty}</p>;
  return (
    <table style={styles.table}>
      <thead>
        <tr>
          {showWorker && <th style={styles.th}>Worker</th>}
          <th style={styles.th}>When</th>
          <th style={styles.th}>Type</th>
          <th style={{ ...styles.th, textAlign: "right" }}>Days</th>
          <th style={styles.th}>Status</th>
          <th style={styles.th}>Note</th>
          <th style={styles.th} />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const [label, color] = STATUS[row.status];
          const waiting = row.status === "requested";
          const open = waiting || row.status === "approved";
          return (
            <tr key={row.id}>
              {showWorker && <td style={styles.td}>{row.worker_name}</td>}
              <td style={styles.td}>{dayRange(row)}</td>
              <td style={styles.td}>
                {row.type_name}
                {!row.paid && <span style={{ color: "var(--muted)" }}> · unpaid</span>}
              </td>
              <td style={{ ...styles.td, textAlign: "right" }}>{Number(row.days)}</td>
              <td style={styles.td}>
                <Badge color={color}>{label}</Badge>
              </td>
              <td style={{ ...styles.td, color: "var(--muted)" }}>{row.note}</td>
              <td style={{ ...styles.td, whiteSpace: "nowrap", textAlign: "right" }}>
                {canManage && waiting && (
                  <>
                    <button type="button" style={styles.button} onClick={() => onAction(row, "approve")}>
                      Approve
                    </button>{" "}
                    <button type="button" style={styles.quiet} onClick={() => onAction(row, "reject")}>
                      Reject
                    </button>{" "}
                  </>
                )}
                {open && (canManage || (waiting && row.requested_by === userId)) && (
                  <button type="button" style={styles.danger} onClick={() => onAction(row, "cancel")}>
                    {waiting && !canManage ? "Withdraw" : "Cancel"}
                  </button>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export function BalanceTiles({ balance }) {
  if (!balance) return null;
  const tiles = [
    ["Vacation per year", balance.allowance],
    ["Taken", balance.used],
    ["Planned", balance.planned],
    ["Waiting", balance.waiting],
    ["Left", balance.left],
  ];
  return (
    <div style={styles.stats}>
      {tiles.map(([label, value]) => (
        <div key={label} style={styles.stat}>
          <div style={styles.label}>{label}</div>
          <strong>{Number(value)}</strong>
        </div>
      ))}
    </div>
  );
}
