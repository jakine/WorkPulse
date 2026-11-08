import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiList } from "../api/client";
import { DayOffForm, DayOffList } from "../components/DaysOff";
import { addDays, isoDate, parseDate } from "../components/ReportCalendar";
import { ErrorText, PageHeader, companyToday, styles } from "../components/ui";
import { useAuth, useRole } from "../context/AuthContext";

function Balances({ rows, year, onYear }) {
  return (
    <div style={styles.card}>
      <div style={{ display: "flex", gap: "0.8rem", alignItems: "center", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>Vacation left</h2>
        <select style={{ ...styles.input, width: "auto" }} value={year} onChange={(e) => onYear(Number(e.target.value))}>
          {[year - 1, year, year + 1].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </div>
      {rows.length === 0 ? (
        <p style={{ color: "var(--muted)" }}>No workers.</p>
      ) : (
        <table style={{ ...styles.table, marginTop: "0.8rem" }}>
          <thead>
            <tr>
              <th style={styles.th}>Worker</th>
              {["Per year", "Taken", "Planned", "Waiting", "Left"].map((label) => (
                <th key={label} style={{ ...styles.th, textAlign: "right" }}>
                  {label}
                </th>
              ))}
              <th style={styles.th}>Other days off</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const other = Object.entries(row.by_type).filter(([code]) => code !== "V");
              return (
                <tr key={row.worker}>
                  <td style={styles.td}>
                    <Link to={`/workers/${row.worker}?tab=days-off`}>{row.name}</Link>
                  </td>
                  {["allowance", "used", "planned", "waiting", "left"].map((key) => (
                    <td
                      key={key}
                      style={{ ...styles.td, textAlign: "right", fontWeight: key === "left" ? 650 : 400, color: key === "left" && Number(row.left) < 0 ? "var(--danger)" : undefined }}
                    >
                      {Number(row[key])}
                    </td>
                  ))}
                  <td style={{ ...styles.td, color: "var(--muted)" }}>
                    {other.length ? other.map(([code, days]) => `${code} ${Number(days)}`).join(" · ") : "–"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function DaysOffPage() {
  const { user } = useAuth();
  const { canManage } = useRole();
  const today = companyToday(user?.active_company);
  const [year, setYear] = useState(Number(today.slice(0, 4)));
  const [workers, setWorkers] = useState([]);
  const [types, setTypes] = useState([]);
  const [waiting, setWaiting] = useState([]);
  const [recent, setRecent] = useState([]);
  const [balances, setBalances] = useState([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const since = isoDate(addDays(parseDate(today), -30));
    const [workerRows, teamRows, typeRows, waitingRows, recentRows, balanceRows] = await Promise.all([
      apiList("/workers/"),
      apiList("/teams/"),
      apiList("/leave-types/"),
      apiList("/days-off/?status=requested"),
      apiList(`/days-off/?status=approved&from=${since}`),
      apiList(`/days-off/balances/?year=${year}`),
    ]);
    const myTeams = new Set(teamRows.filter((team) => team.lead_user === user?.id).map((team) => team.id));
    setWorkers(workerRows.filter((worker) => worker.status === "active" && (canManage || myTeams.has(worker.team))));
    setTypes(typeRows);
    setWaiting(waitingRows);
    setRecent(recentRows);
    setBalances(balanceRows);
  }, [today, year, canManage, user?.id]);

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [load]);

  async function act(row, action) {
    setError("");
    try {
      await api(`/days-off/${row.id}/${action}/`, { method: "POST" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={styles.page}>
      <PageHeader title="Days off">
        Vacation, sick days and other days off. {canManage ? "Days you add are approved at once." : "Your requests wait for a manager."}
      </PageHeader>
      <ErrorText>{error}</ErrorText>

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Waiting for approval</h2>
        <DayOffList rows={waiting} canManage={canManage} userId={user?.id} onAction={act} empty="Nothing is waiting." />
      </div>

      <DayOffForm
        workers={workers}
        types={types}
        canManage={canManage}
        today={today}
        onSaved={() => load().catch((err) => setError(err.message))}
        onError={setError}
      />

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Upcoming and recent</h2>
        <DayOffList rows={recent} canManage={canManage} userId={user?.id} onAction={act} empty="No days off in the last month or ahead." />
      </div>

      <Balances rows={balances} year={year} onYear={setYear} />
    </div>
  );
}

export default DaysOffPage;
