import { useCallback, useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { api, apiList } from "../api/client";
import { METHODS, formatMoney, num, payTypeLabel } from "../components/money";
import { Badge, ErrorText, Field, PageHeader, companyToday, styles } from "../components/ui";
import { useAuth, useRole } from "../context/AuthContext";

const numHead = { ...styles.th, textAlign: "right" };

function Owed({ rows, currency }) {
  const total = rows.reduce((sum, row) => sum + Number(row.owed), 0);
  return (
    <div style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Owed now</h2>
      {rows.length === 0 ? (
        <p style={{ margin: 0 }}>Everyone is paid up.</p>
      ) : (
        <>
          <p style={{ marginTop: 0 }}>
            {formatMoney(total, currency)} in all. A minus means the worker has had more in advances than they've earned so far.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem 1.2rem" }}>
            {rows.map((row) => (
              <span key={row.worker}>
                <Link to={`/workers/${row.worker}?tab=pay`}>{row.name}</Link>{" "}
                <strong style={{ color: Number(row.owed) < 0 ? "var(--danger)" : "inherit" }}>{formatMoney(row.owed, currency)}</strong>
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function RunView({ data, today, onAct }) {
  const currency = data.currency;
  const run = data.run;
  const approved = run?.status === "approved";
  const missing = data.lines.filter((line) => line.missing_rate);
  const total = (key) => data.lines.reduce((sum, line) => sum + Number(line[key]), 0);

  function markPaid(line) {
    const amount = window.prompt(`Pay ${line.worker_name} how much? (${currency})`, Number(line.owed_now).toFixed(2));
    if (!amount) return;
    onAct(() =>
      api("/payments/", {
        method: "POST",
        body: { worker: line.worker, paid_on: today, amount: Number(amount), kind: "wages", method: "cash" },
      })
    );
  }

  return (
    <div style={styles.card}>
      <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>
          {data.pay_group.name}, {data.period.label}
        </h2>
        <Badge color={data.period.hours_status === "approved" ? "var(--accent)" : "var(--muted)"}>
          Hours {data.period.hours_status === "approved" ? "approved" : "open"}
        </Badge>
        <Badge color={approved ? "var(--accent)" : "var(--muted)"}>{approved ? "Pay approved" : "Draft"}</Badge>
        {!approved && data.period.hours_status === "approved" && (
          <button
            type="button"
            style={styles.button}
            disabled={missing.length > 0}
            onClick={() =>
              window.confirm(`Approve pay for ${data.pay_group.name}, ${data.period.label}? The amounts will be frozen.`) &&
              onAct(() =>
                api("/pay-runs/approve/", {
                  method: "POST",
                  body: { pay_group: data.pay_group.id, start_date: data.period.start, end_date: data.period.end },
                })
              )
            }
          >
            Approve pay
          </button>
        )}
        {approved && (
          <>
            <a href={`/api/pay-runs/${run.id}/export/`} style={{ ...styles.quiet, textDecoration: "none" }}>
              Export CSV
            </a>
            <button
              type="button"
              style={styles.quiet}
              onClick={() => window.confirm("Reopen this pay? Its lines will be calculated again.") && onAct(() => api(`/pay-runs/${run.id}/reopen/`, { method: "POST" }))}
            >
              Reopen
            </button>
          </>
        )}
      </div>
      {data.period.hours_status !== "approved" && (
        <p>
          These amounts are a preview. A manager approves the hours in the <Link to="/timesheets">timesheet</Link> before pay can be approved.
        </p>
      )}
      {missing.length > 0 && (
        <p style={{ color: "var(--danger)" }}>
          No pay rate for{" "}
          {missing.map((line, index) => (
            <span key={line.worker}>
              {index > 0 && ", "}
              <Link to={`/workers/${line.worker}?tab=pay`}>{line.worker_name}</Link>
            </span>
          ))}
          . Add one before approving.
        </p>
      )}
      {data.lines.length === 0 ? (
        <p>Nobody to pay in this period.</p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Worker</th>
                <th style={styles.th}>Rate</th>
                <th style={numHead}>Days</th>
                <th style={numHead}>Extra h</th>
                <th style={numHead}>Days off</th>
                <th style={numHead}>Base</th>
                <th style={numHead}>Extra</th>
                <th style={numHead}>Days off & holidays</th>
                <th style={numHead}>Bonus − deduct.</th>
                <th style={numHead}>Net</th>
                <th style={numHead}>Owed before</th>
                <th style={numHead}>To pay</th>
                <th style={numHead}>Owed now</th>
                <th style={styles.th} />
              </tr>
            </thead>
            <tbody>
              {data.lines.map((line) => (
                <tr key={line.worker}>
                  <td style={styles.td}>
                    <Link to={`/workers/${line.worker}?tab=pay`}>{line.worker_name}</Link>
                    {line.breakdown?.warnings?.length > 0 && (
                      <div style={{ color: "var(--warn)", fontSize: "0.78rem" }}>{line.breakdown.warnings.join(" ")}</div>
                    )}
                  </td>
                  <td style={{ ...styles.td, whiteSpace: "nowrap" }}>
                    {line.missing_rate ? (
                      <Badge color="var(--danger)">No rate</Badge>
                    ) : (
                      `${formatMoney(line.rate, currency)} ${payTypeLabel(line.pay_type).toLowerCase()}`
                    )}
                  </td>
                  <td style={num}>{Number(line.days)}</td>
                  <td style={num}>{Number(line.extra_hours) || "–"}</td>
                  <td style={num} title="Paid / unpaid">
                    {Number(line.paid_off_days) || Number(line.unpaid_off_days) ? `${Number(line.paid_off_days)} / ${Number(line.unpaid_off_days)}` : "–"}
                  </td>
                  <td style={num}>{formatMoney(line.base, currency)}</td>
                  <td style={num}>{Number(line.extra_pay) ? formatMoney(line.extra_pay, currency) : "–"}</td>
                  <td style={num}>
                    {Number(line.off_pay) + Number(line.holiday_pay) ? formatMoney(Number(line.off_pay) + Number(line.holiday_pay), currency) : "–"}
                  </td>
                  <td style={num}>
                    {Number(line.bonuses) - Number(line.deductions) ? formatMoney(Number(line.bonuses) - Number(line.deductions), currency) : "–"}
                  </td>
                  <td style={{ ...num, fontWeight: 650 }}>{formatMoney(line.net, currency)}</td>
                  <td style={num}>{formatMoney(line.balance_before, currency)}</td>
                  <td style={{ ...num, fontWeight: 650 }}>{formatMoney(line.to_pay, currency)}</td>
                  <td style={{ ...num, color: Number(line.owed_now) > 0 ? "var(--accent)" : "var(--muted)" }}>
                    {formatMoney(line.owed_now, currency)}
                  </td>
                  <td style={{ ...styles.td, whiteSpace: "nowrap" }}>
                    {approved && Number(line.owed_now) > 0 && (
                      <button type="button" style={styles.quiet} onClick={() => markPaid(line)}>
                        Mark paid
                      </button>
                    )}{" "}
                    {line.id && <Link to={`/pay/lines/${line.id}`}>Payslip</Link>}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th style={styles.th} colSpan={9}>
                  Total
                </th>
                <th style={numHead}>{formatMoney(total("net"), currency)}</th>
                <th style={numHead} />
                <th style={numHead}>{formatMoney(total("to_pay"), currency)}</th>
                <th style={numHead}>{formatMoney(total("owed_now"), currency)}</th>
                <th style={styles.th} />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}

function RecordAdvance({ workers, today, currency, onAct }) {
  const empty = { worker: "", paid_on: today, amount: "", method: "cash", note: "" };
  const [form, setForm] = useState(empty);

  async function submit(event) {
    event.preventDefault();
    const ok = await onAct(() =>
      api("/payments/", { method: "POST", body: { ...form, worker: Number(form.worker), amount: Number(form.amount), kind: "advance" } })
    );
    if (ok) setForm(empty);
  }

  return (
    <form onSubmit={submit} style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Record an advance</h2>
      <p style={{ marginTop: 0 }}>Cash handed over before payday. It comes off the next pay.</p>
      <div style={styles.row}>
        <Field label="Worker">
          <select style={styles.input} value={form.worker} onChange={(e) => setForm({ ...form, worker: e.target.value })} required>
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
        <Field label="Date">
          <input style={styles.input} type="date" value={form.paid_on} onChange={(e) => setForm({ ...form, paid_on: e.target.value })} required />
        </Field>
        <Field label={`Amount (${currency})`}>
          <input
            style={{ ...styles.input, width: "7rem", minWidth: 0 }}
            type="number"
            min="0.01"
            step="0.01"
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
            required
          />
        </Field>
        <Field label="How">
          <select style={styles.input} value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}>
            {METHODS.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Note">
          <input style={styles.input} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </Field>
        <button style={styles.button} type="submit">
          Record
        </button>
      </div>
    </form>
  );
}

function PaySettingsForm({ settings, onAct }) {
  const [form, setForm] = useState(() => ({
    currency: settings.currency,
    extra_hours_multiplier: settings.extra_hours_multiplier ?? "",
    pay_holidays_for_day_rate: settings.pay_holidays_for_day_rate,
  }));

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onAct(() =>
          api("/pay/settings/", {
            method: "PATCH",
            body: { ...form, extra_hours_multiplier: form.extra_hours_multiplier === "" ? null : Number(form.extra_hours_multiplier) },
          })
        );
      }}
      style={styles.card}
    >
      <h2 style={{ marginTop: 0 }}>Pay settings</h2>
      <div style={styles.row}>
        <Field label="Currency">
          <input
            style={{ ...styles.input, width: "5rem", minWidth: 0 }}
            maxLength={3}
            value={form.currency}
            onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
            required
          />
        </Field>
        <Field label="Extra hours paid at">
          <input
            style={{ ...styles.input, width: "6rem", minWidth: 0 }}
            type="number"
            min="0"
            step="0.05"
            placeholder="Not paid"
            value={form.extra_hours_multiplier}
            onChange={(e) => setForm({ ...form, extra_hours_multiplier: e.target.value })}
            title="1 pays extra hours at the normal rate, 1.5 at time and a half. Empty: extra hours aren't paid."
          />
        </Field>
        <label style={{ display: "flex", gap: "0.35rem", alignItems: "center", paddingBottom: "0.55rem" }}>
          <input
            type="checkbox"
            checked={form.pay_holidays_for_day_rate}
            onChange={(e) => setForm({ ...form, pay_holidays_for_day_rate: e.target.checked })}
          />
          Pay day-rate workers for holidays
        </label>
        <button style={styles.button} type="submit">
          Save
        </button>
      </div>
      <p style={{ marginBottom: 0, color: "var(--muted)", fontSize: "0.85rem" }}>
        Extra hours are hours past the schedule (for day rates, past a full day). Fixed weekly and monthly amounts are shared over the
        scheduled days of each week or month.
      </p>
    </form>
  );
}

function PayPage() {
  const { user } = useAuth();
  const { isOwner } = useRole();
  const today = companyToday(user?.active_company);
  const [groups, setGroups] = useState([]);
  const [group, setGroup] = useState("");
  const [periods, setPeriods] = useState([]);
  const [selected, setSelected] = useState(null);
  const [view, setView] = useState(null);
  const [owedRows, setOwedRows] = useState([]);
  const [settings, setSettings] = useState(null);
  const [workers, setWorkers] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isOwner) return;
    Promise.all([apiList("/pay-groups/"), apiList("/workers/")])
      .then(([groupRows, workerRows]) => {
        setGroups(groupRows);
        setWorkers(workerRows.filter((worker) => worker.status === "active"));
        setGroup((current) => current || String((groupRows.find((row) => row.is_default) || groupRows[0] || {}).id || ""));
      })
      .catch((err) => setError(err.message));
  }, [isOwner]);

  const load = useCallback(async () => {
    if (!isOwner) return;
    const [owedData, settingsData] = await Promise.all([api("/pay/owed/"), api("/pay/settings/")]);
    setOwedRows(owedData);
    setSettings(settingsData);
    if (!group) return;
    const periodRows = await api(`/pay-runs/periods/?pay_group=${group}`);
    setPeriods(periodRows);
    const chosen = selected || (periodRows.find((row) => row.over) || periodRows[0])?.start;
    if (chosen) setView(await api(`/pay-runs/view/?pay_group=${group}&date=${chosen}`));
  }, [isOwner, group, selected]);

  useEffect(() => {
    setError("");
    load().catch((err) => setError(err.message));
  }, [load]);

  async function act(action) {
    setError("");
    try {
      await action();
      await load();
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    }
  }

  if (!isOwner) return <Navigate to="/dashboard" replace />;

  const currency = settings?.currency || "EUR";
  return (
    <div style={styles.page}>
      <PageHeader title="Pay">Only you, the owner, can see this page.</PageHeader>
      <ErrorText>{error}</ErrorText>
      <Owed rows={owedRows} currency={currency} />

      <div style={styles.card}>
        <div style={{ display: "flex", gap: "0.8rem", alignItems: "center", flexWrap: "wrap" }}>
          <h2 style={{ margin: 0 }}>Periods</h2>
          <select
            style={{ ...styles.input, width: "auto" }}
            value={group}
            onChange={(e) => {
              setGroup(e.target.value);
              setSelected(null);
              setView(null);
            }}
            aria-label="Pay group"
          >
            {groups.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
        </div>
        <table style={{ ...styles.table, marginTop: "0.8rem" }}>
          <thead>
            <tr>
              <th style={styles.th}>Period</th>
              <th style={styles.th}>Hours</th>
              <th style={styles.th}>Pay</th>
              <th style={numHead}>Net</th>
              <th style={numHead}>To pay</th>
            </tr>
          </thead>
          <tbody>
            {periods.map((row) => (
              <tr key={row.start} style={{ background: view?.period.start === row.start ? "var(--surface-2)" : "transparent" }}>
                <td style={styles.td}>
                  <button
                    type="button"
                    className="ghost-btn"
                    onClick={() => setSelected(row.start)}
                    style={{ fontWeight: view?.period.start === row.start ? 700 : 400 }}
                  >
                    {row.label}
                  </button>
                  {!row.over && <span style={{ color: "var(--muted)", fontSize: "0.8rem" }}> (running)</span>}
                </td>
                <td style={styles.td}>{row.hours_status === "approved" ? "Approved" : "Open"}</td>
                <td style={styles.td}>{row.pay_status === "approved" ? "Approved" : row.pay_status === "draft" ? "Reopened" : "–"}</td>
                <td style={num}>{row.net ? formatMoney(row.net, currency) : "–"}</td>
                <td style={num}>{row.to_pay ? formatMoney(row.to_pay, currency) : "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {view && <RunView data={view} today={today} onAct={act} />}
      <RecordAdvance workers={workers} today={today} currency={currency} onAct={act} />
      {settings && <PaySettingsForm key={JSON.stringify(settings)} settings={settings} onAct={act} />}
    </div>
  );
}

export default PayPage;
