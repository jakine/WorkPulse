import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { formatMoney, payTypeLabel } from "../components/money";
import { ErrorText, formatDay, styles } from "../components/ui";
import { useRole } from "../context/AuthContext";

const row = { display: "flex", justifyContent: "space-between", gap: "1rem", padding: "0.3rem 0", borderBottom: "1px solid var(--line)" };
const total = { ...row, fontWeight: 700, borderBottom: "2px solid var(--line-strong)" };

function Amount({ label, value, currency, strong, note }) {
  return (
    <div style={strong ? total : row}>
      <span>
        {label}
        {note && <span style={{ color: "var(--muted)", fontWeight: 400 }}> · {note}</span>}
      </span>
      <span style={{ fontVariantNumeric: "tabular-nums" }}>{formatMoney(value, currency)}</span>
    </div>
  );
}

function PayslipPage() {
  const { id } = useParams();
  const { isOwner } = useRole();
  const [slip, setSlip] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isOwner) return;
    api(`/pay-lines/${id}/`)
      .then(setSlip)
      .catch((err) => setError(err.message));
  }, [id, isOwner]);

  if (!isOwner) return <Navigate to="/dashboard" replace />;
  if (!slip) return <ErrorText>{error || "Loading..."}</ErrorText>;

  const currency = slip.currency;
  const bonuses = slip.adjustments.filter((item) => item.kind === "bonus");
  const deductions = slip.adjustments.filter((item) => item.kind === "deduction");
  const days = [
    ["Days worked", slip.days],
    ["Hours", slip.hours],
    ["Extra hours", slip.extra_hours],
    ["Paid days off", slip.paid_off_days],
    ["Unpaid days off", slip.unpaid_off_days],
    ["Holidays", slip.holidays],
  ];

  return (
    <div style={styles.page}>
      <div className="no-print" style={{ display: "flex", gap: "0.8rem", alignItems: "center" }}>
        <Link to="/pay">← Pay</Link>
        <button type="button" style={styles.button} onClick={() => window.print()}>
          Print
        </button>
      </div>
      <div className="payslip" style={{ ...styles.card, maxWidth: "40rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
          <div>
            <div style={{ color: "var(--muted)" }}>{slip.company_name}</div>
            <h1 style={{ margin: "0.2rem 0" }}>Payslip</h1>
            <h2 style={{ margin: 0 }}>{slip.worker_name}</h2>
          </div>
          <div style={{ textAlign: "right" }}>
            <div>
              <strong>{slip.period.label}</strong>
            </div>
            <div style={{ color: "var(--muted)" }}>{slip.pay_group_name}</div>
            <div style={{ color: "var(--muted)" }}>
              {formatMoney(slip.rate, currency)} {payTypeLabel(slip.pay_type).toLowerCase()}
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(8rem, 1fr))", gap: "0.6rem", margin: "1rem 0" }}>
          {days.map(([label, value]) => (
            <div key={label}>
              <div style={styles.label}>{label}</div>
              <strong>{Number(value)}</strong>
            </div>
          ))}
        </div>

        <Amount label="Base pay" value={slip.base} currency={currency} />
        {Number(slip.extra_pay) > 0 && <Amount label="Extra hours" value={slip.extra_pay} currency={currency} />}
        {Number(slip.off_pay) > 0 && <Amount label="Paid days off" value={slip.off_pay} currency={currency} />}
        {Number(slip.holiday_pay) > 0 && <Amount label="Holidays" value={slip.holiday_pay} currency={currency} />}
        {bonuses.map((item) => (
          <Amount key={item.id} label="Bonus" note={item.note || formatDay(item.date)} value={item.amount} currency={currency} />
        ))}
        <Amount label="Gross" value={slip.gross} currency={currency} strong />
        {deductions.map((item) => (
          <Amount key={item.id} label="Deduction" note={item.note || formatDay(item.date)} value={-Number(item.amount)} currency={currency} />
        ))}
        <Amount label="Net for this period" value={slip.net} currency={currency} strong />
        <Amount
          label={Number(slip.balance_before) < 0 ? "Advances and earlier balance" : "Owed from before"}
          note={slip.advances.length ? `advances: ${slip.advances.map((item) => `${formatDay(item.paid_on)} ${formatMoney(item.amount, currency)}`).join(", ")}` : ""}
          value={slip.balance_before}
          currency={currency}
        />
        <Amount label="To pay" value={slip.to_pay} currency={currency} strong />

        {slip.breakdown?.segments?.length > 0 && (
          <p style={{ color: "var(--muted)", fontSize: "0.82rem" }}>
            Fixed pay:{" "}
            {slip.breakdown.segments
              .map((part) => `${formatDay(part.from)} – ${formatDay(part.to)}: ${part.days} of ${part.out_of} scheduled days, ${formatMoney(part.value, currency)}`)
              .join("; ")}
            .
          </p>
        )}
        {slip.breakdown?.unrecorded > 0 && (
          <p style={{ color: "var(--muted)", fontSize: "0.82rem" }}>
            {slip.breakdown.unrecorded} scheduled day{slip.breakdown.unrecorded === 1 ? "" : "s"} had no hours recorded and were paid as usual.
          </p>
        )}
      </div>
    </div>
  );
}

export default PayslipPage;
