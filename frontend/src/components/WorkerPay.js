import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiList } from "../api/client";
import { METHODS, PAY_TYPES, formatMoney, num, payTypeLabel } from "./money";
import { Badge, Field, formatDay, labelFor, styles } from "./ui";

const small = { ...styles.input, width: "7rem", minWidth: 0 };

function WorkerPay({ worker, today, onError }) {
  const [currency, setCurrency] = useState("EUR");
  const [rates, setRates] = useState([]);
  const [adjustments, setAdjustments] = useState([]);
  const [payments, setPayments] = useState([]);
  const [lines, setLines] = useState([]);
  const [owed, setOwed] = useState("0");
  const [rate, setRate] = useState({ start_date: today, pay_type: "daily", amount: "", note: "" });
  const [adjustment, setAdjustment] = useState({ date: today, kind: "bonus", amount: "", note: "" });
  const [payment, setPayment] = useState({ paid_on: today, amount: "", kind: "advance", method: "cash", note: "" });

  const load = useCallback(async () => {
    const [settings, rateRows, adjustmentRows, paymentRows, lineRows, owedRows] = await Promise.all([
      api("/pay/settings/"),
      apiList(`/pay-rates/?worker=${worker.id}`),
      apiList(`/pay-adjustments/?worker=${worker.id}`),
      apiList(`/payments/?worker=${worker.id}`),
      apiList(`/pay-lines/?worker=${worker.id}`),
      apiList("/pay/owed/"),
    ]);
    setCurrency(settings.currency);
    setRates(rateRows);
    setAdjustments(adjustmentRows);
    setPayments(paymentRows);
    setLines(lineRows);
    setOwed((owedRows.find((row) => row.worker === worker.id) || { owed: "0" }).owed);
  }, [worker.id]);

  useEffect(() => {
    load().catch((err) => onError(err.message));
  }, [load, onError]);

  async function run(action) {
    onError("");
    try {
      await action();
      await load();
      return true;
    } catch (err) {
      onError(err.message);
      return false;
    }
  }

  async function addRate(event) {
    event.preventDefault();
    const ok = await run(() => api("/pay-rates/", { method: "POST", body: { ...rate, worker: worker.id, amount: Number(rate.amount || 0) } }));
    if (ok) setRate({ start_date: today, pay_type: rate.pay_type, amount: "", note: "" });
  }

  async function addAdjustment(event) {
    event.preventDefault();
    const ok = await run(() =>
      api("/pay-adjustments/", { method: "POST", body: { ...adjustment, worker: worker.id, amount: Number(adjustment.amount) } })
    );
    if (ok) setAdjustment({ date: today, kind: adjustment.kind, amount: "", note: "" });
  }

  async function addPayment(event) {
    event.preventDefault();
    const ok = await run(() => api("/payments/", { method: "POST", body: { ...payment, worker: worker.id, amount: Number(payment.amount) } }));
    if (ok) setPayment({ paid_on: today, amount: "", kind: payment.kind, method: payment.method, note: "" });
  }

  const current = [...rates].reverse().find((row) => row.start_date <= today);
  return (
    <>
      <div style={styles.stats}>
        <div style={styles.stat}>
          <div style={styles.label}>Rate now</div>
          <strong>{current ? `${formatMoney(current.amount, currency)} ${payTypeLabel(current.pay_type).toLowerCase()}` : "No rate"}</strong>
        </div>
        <div style={styles.stat}>
          <div style={styles.label}>{Number(owed) < 0 ? "Owes you (advances)" : "Owed now"}</div>
          <strong style={{ color: Number(owed) < 0 ? "var(--danger)" : "inherit" }}>{formatMoney(Math.abs(Number(owed)), currency)}</strong>
        </div>
      </div>

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Pay rate</h2>
        <p style={{ marginTop: 0 }}>A new rate applies from its start day; earlier days keep the rate they had.</p>
        {rates.length > 0 && (
          <table style={styles.table}>
            <tbody>
              {[...rates].reverse().map((row) => (
                <tr key={row.id}>
                  <td style={styles.td}>From {formatDay(row.start_date)}</td>
                  <td style={styles.td}>{payTypeLabel(row.pay_type)}</td>
                  <td style={num}>{row.pay_type === "not_paid_here" ? "–" : formatMoney(row.amount, currency)}</td>
                  <td style={{ ...styles.td, color: "var(--muted)" }}>{row.note}</td>
                  <td style={{ ...styles.td, textAlign: "right" }}>
                    <button type="button" style={styles.danger} onClick={() => run(() => api(`/pay-rates/${row.id}/`, { method: "DELETE" }))}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <form onSubmit={addRate} style={{ ...styles.row, marginTop: "0.8rem" }}>
          <Field label="From">
            <input style={styles.input} type="date" value={rate.start_date} onChange={(e) => setRate({ ...rate, start_date: e.target.value })} required />
          </Field>
          <Field label="Paid">
            <select style={styles.input} value={rate.pay_type} onChange={(e) => setRate({ ...rate, pay_type: e.target.value })}>
              {PAY_TYPES.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          {rate.pay_type !== "not_paid_here" && (
            <Field label={`Amount (${currency})`}>
              <input style={small} type="number" min="0" step="0.01" value={rate.amount} onChange={(e) => setRate({ ...rate, amount: e.target.value })} required />
            </Field>
          )}
          <Field label="Note">
            <input style={styles.input} value={rate.note} onChange={(e) => setRate({ ...rate, note: e.target.value })} />
          </Field>
          <button style={styles.button} type="submit">
            Set rate
          </button>
        </form>
      </div>

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Bonuses and deductions</h2>
        <p style={{ marginTop: 0 }}>Each one goes into the next pay approved after its date, then can't change.</p>
        {adjustments.length > 0 && (
          <table style={styles.table}>
            <tbody>
              {adjustments.map((row) => (
                <tr key={row.id}>
                  <td style={styles.td}>{formatDay(row.date)}</td>
                  <td style={styles.td}>{row.kind === "bonus" ? "Bonus" : "Deduction"}</td>
                  <td style={num}>{formatMoney(row.kind === "bonus" ? row.amount : -Number(row.amount), currency)}</td>
                  <td style={{ ...styles.td, color: "var(--muted)" }}>{row.note}</td>
                  <td style={{ ...styles.td, textAlign: "right" }}>
                    {row.settled ? (
                      <Badge color="var(--muted)">In approved pay</Badge>
                    ) : (
                      <button type="button" style={styles.danger} onClick={() => run(() => api(`/pay-adjustments/${row.id}/`, { method: "DELETE" }))}>
                        Remove
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <form onSubmit={addAdjustment} style={{ ...styles.row, marginTop: "0.8rem" }}>
          <Field label="Date">
            <input style={styles.input} type="date" value={adjustment.date} onChange={(e) => setAdjustment({ ...adjustment, date: e.target.value })} required />
          </Field>
          <Field label="Kind">
            <select style={styles.input} value={adjustment.kind} onChange={(e) => setAdjustment({ ...adjustment, kind: e.target.value })}>
              <option value="bonus">Bonus</option>
              <option value="deduction">Deduction</option>
            </select>
          </Field>
          <Field label={`Amount (${currency})`}>
            <input
              style={small}
              type="number"
              min="0.01"
              step="0.01"
              value={adjustment.amount}
              onChange={(e) => setAdjustment({ ...adjustment, amount: e.target.value })}
              required
            />
          </Field>
          <Field label="Note">
            <input style={styles.input} value={adjustment.note} onChange={(e) => setAdjustment({ ...adjustment, note: e.target.value })} />
          </Field>
          <button style={styles.button} type="submit">
            Add
          </button>
        </form>
      </div>

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Payments</h2>
        {payments.length > 0 && (
          <table style={styles.table}>
            <tbody>
              {payments.map((row) => (
                <tr key={row.id}>
                  <td style={styles.td}>{formatDay(row.paid_on)}</td>
                  <td style={styles.td}>{row.kind === "advance" ? "Advance" : "Wages"}</td>
                  <td style={num}>{formatMoney(row.amount, currency)}</td>
                  <td style={styles.td}>{labelFor(METHODS, row.method)}</td>
                  <td style={{ ...styles.td, color: "var(--muted)" }}>{row.note}</td>
                  <td style={{ ...styles.td, textAlign: "right" }}>
                    <button
                      type="button"
                      style={styles.danger}
                      onClick={() => window.confirm("Delete this payment?") && run(() => api(`/payments/${row.id}/`, { method: "DELETE" }))}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <form onSubmit={addPayment} style={{ ...styles.row, marginTop: "0.8rem" }}>
          <Field label="Date">
            <input style={styles.input} type="date" value={payment.paid_on} onChange={(e) => setPayment({ ...payment, paid_on: e.target.value })} required />
          </Field>
          <Field label="Kind">
            <select style={styles.input} value={payment.kind} onChange={(e) => setPayment({ ...payment, kind: e.target.value })}>
              <option value="advance">Advance</option>
              <option value="wages">Wages</option>
            </select>
          </Field>
          <Field label={`Amount (${currency})`}>
            <input
              style={small}
              type="number"
              min="0.01"
              step="0.01"
              value={payment.amount}
              onChange={(e) => setPayment({ ...payment, amount: e.target.value })}
              required
            />
          </Field>
          <Field label="How">
            <select style={styles.input} value={payment.method} onChange={(e) => setPayment({ ...payment, method: e.target.value })}>
              {METHODS.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Note">
            <input style={styles.input} value={payment.note} onChange={(e) => setPayment({ ...payment, note: e.target.value })} />
          </Field>
          <button style={styles.button} type="submit">
            Record
          </button>
        </form>
      </div>

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Pay history</h2>
        {lines.length === 0 ? (
          <p style={{ margin: 0 }}>No approved pay yet.</p>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Period</th>
                <th style={{ ...styles.th, textAlign: "right" }}>Days</th>
                <th style={{ ...styles.th, textAlign: "right" }}>Net</th>
                <th style={{ ...styles.th, textAlign: "right" }}>To pay</th>
                <th style={styles.th} />
              </tr>
            </thead>
            <tbody>
              {lines.map((line) => (
                <tr key={line.id}>
                  <td style={styles.td}>
                    {line.pay_group_name}, {line.period_label}
                  </td>
                  <td style={num}>{Number(line.days)}</td>
                  <td style={num}>{formatMoney(line.net, currency)}</td>
                  <td style={num}>{formatMoney(line.to_pay, currency)}</td>
                  <td style={{ ...styles.td, textAlign: "right" }}>
                    <Link to={`/pay/lines/${line.id}`}>Payslip</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

export default WorkerPay;
