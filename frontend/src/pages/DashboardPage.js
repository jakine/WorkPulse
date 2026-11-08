import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiList } from "../api/client";
import { ProgressMeter, StatusBadge } from "../components/charts";
import { formatMoney } from "../components/money";
import { addDays, isoDate, parseDate } from "../components/ReportCalendar";
import { Badge, ErrorText, PageHeader, companyToday, formatDay, styles } from "../components/ui";
import { useAuth, useRole } from "../context/AuthContext";

function OwedTile() {
  const [rows, setRows] = useState(null);

  useEffect(() => {
    api("/pay/owed/")
      .then(setRows)
      .catch(() => setRows(null));
  }, []);

  if (!rows) return null;
  const total = rows.reduce((sum, row) => sum + Math.max(0, Number(row.owed)), 0);
  return (
    <div style={styles.card}>
      <h2>Owed to workers</h2>
      <p style={{ margin: 0 }}>
        <Link to="/pay">
          {total > 0 ? `${formatMoney(total)} still to pay to ${rows.filter((row) => Number(row.owed) > 0).length} people` : "Everyone is paid up."}
        </Link>
      </p>
    </div>
  );
}

function PeopleToday({ company, canManage }) {
  const today = companyToday(company);
  const yesterday = isoDate(addDays(parseDate(today), -1));
  const [off, setOff] = useState([]);
  const [waiting, setWaiting] = useState(0);
  const [missing, setMissing] = useState([]);
  const [due, setDue] = useState([]);

  useEffect(() => {
    // Loaded apart from the main dashboard, so one failing call can't blank the page.
    apiList(`/days-off/?status=approved&from=${today}&to=${today}`)
      .then(setOff)
      .catch(() => setOff([]));
    api(`/timesheets/?from=${yesterday}&to=${yesterday}`)
      .then((sheet) => setMissing(sheet.workers.filter((row) => row.cells[yesterday]?.flags.includes("missing"))))
      .catch(() => setMissing([]));
    if (canManage) {
      api("/days-off/?status=requested&page_size=1")
        .then((data) => setWaiting(data.count || 0))
        .catch(() => setWaiting(0));
      api("/timesheet-periods/due/")
        .then((rows) => setDue(rows.filter((row) => row.status !== "approved")))
        .catch(() => setDue([]));
    }
  }, [today, yesterday, canManage]);

  return (
    <div style={styles.card}>
      <h2>People today</h2>
      {off.length === 0 ? (
        <p>Nobody is off today.</p>
      ) : (
        <p style={{ display: "flex", gap: "0.4rem 0.8rem", flexWrap: "wrap", alignItems: "center" }}>
          <span>Off today:</span>
          {off.map((row) => (
            <span key={row.id}>
              <Link to={`/workers/${row.worker}?tab=days-off`}>{row.worker_name}</Link> <Badge>{row.type_code}{row.half_day ? " ½" : ""}</Badge>
            </span>
          ))}
        </p>
      )}
      {missing.length > 0 && (
        <p>
          <Link to="/timesheets">
            {missing.length} {missing.length === 1 ? "person has" : "people have"} no hours for yesterday
          </Link>
          : {missing.map((row) => row.name).join(", ")}
        </p>
      )}
      {canManage && waiting > 0 && (
        <p>
          <Link to="/days-off">
            {waiting} day-off request{waiting === 1 ? "" : "s"} waiting for approval
          </Link>
        </p>
      )}
      {due.map((row) => (
        <p key={row.pay_group}>
          <Link to="/timesheets">
            {row.name}, {formatDay(row.start)} – {formatDay(row.end)}: hours ready to approve
          </Link>
        </p>
      ))}
    </div>
  );
}

function DashboardPage() {
  const { user } = useAuth();
  const { canManage, isOwner } = useRole();
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const company = user?.active_company;

  useEffect(() => {
    if (!company) return;
    const until = new Date();
    until.setDate(until.getDate() + 30);
    const expiresBefore = until.toISOString().slice(0, 10);
    Promise.all([
      api("/workers/?page_size=1"),
      api("/projects/?page_size=1"),
      api(`/stock-lots/?expires_before=${expiresBefore}&page_size=5`),
      api("/daily-logs/missing/"),
      api("/progress/"),
      api("/stock-levels/low/"),
    ])
      .then(([workers, workplaces, lots, missing, progress, low]) => {
        setStats({
          workers: workers.count,
          workplaces: workplaces.count,
          expiring: lots.results || [],
          missing: missing.results || [],
          missingDate: missing.date,
          portfolio: progress.results || [],
          low: low || [],
        });
      })
      .catch((err) => setError(err.message));
  }, [company]);

  if (!company) {
    return (
      <div style={styles.card}>
        <h1>Choose a company</h1>
        <p>Create a company or switch to one you already manage.</p>
        <Link to="/company">Go to company</Link>
      </div>
    );
  }

  return (
    <div style={styles.page}>
      <PageHeader title="Home">
        {company.name} — crews, contracts, and what is running out.
      </PageHeader>
      <ErrorText>{error}</ErrorText>
      {stats && (
        <>
          <div style={styles.stats}>
            <div style={styles.stat}>
              <div style={styles.label}>Workers</div>
              <strong style={{ fontFamily: "var(--font-display)", fontSize: "1.7rem" }}>{stats.workers}</strong>
            </div>
            <div style={styles.stat}>
              <div style={styles.label}>Projects</div>
              <strong style={{ fontFamily: "var(--font-display)", fontSize: "1.7rem" }}>{stats.workplaces}</strong>
            </div>
            <div style={styles.stat}>
              <div style={styles.label}>Projects behind</div>
              <strong style={{ fontFamily: "var(--font-display)", fontSize: "1.7rem" }}>
                {stats.portfolio.filter((project) => project.status === "behind").length}
              </strong>
            </div>
            <div style={styles.stat}>
              <div style={styles.label}>Teams not reported today</div>
              <strong style={{ fontFamily: "var(--font-display)", fontSize: "1.7rem" }}>{stats.missing.length}</strong>
            </div>
            <div style={styles.stat}>
              <div style={styles.label}>Lots expiring in 30 days</div>
              <strong style={{ fontFamily: "var(--font-display)", fontSize: "1.7rem" }}>{stats.expiring.length}</strong>
            </div>
          </div>
          <PeopleToday company={company} canManage={canManage} />
          {isOwner && <OwedTile />}
          <div style={styles.card}>
            <h2>Active projects</h2>
            {stats.portfolio.length === 0 ? (
              <p>No active projects.</p>
            ) : (
              <div style={{ display: "grid", gap: "1rem" }}>
                {stats.portfolio.map((project) => (
                  <div
                    key={project.workplace}
                    style={{ display: "grid", gap: "0.5rem", paddingTop: "0.75rem", borderTop: "1px solid var(--line)" }}
                  >
                    <div style={{ display: "flex", gap: "0.5rem 1rem", flexWrap: "wrap", alignItems: "center" }}>
                      <Link to={`/projects/${project.workplace}`}>
                        <strong>{project.name}</strong>
                      </Link>
                      <StatusBadge status={project.status} />
                      {project.forecast_finish && (
                        <span style={{ color: "var(--muted)", fontSize: "0.88rem" }}>
                          Forecast finish {formatDay(project.forecast_finish)}
                        </span>
                      )}
                    </div>
                    {project.scopes.map((scope) => (
                      <div
                        key={scope.scope}
                        style={{
                          display: "grid",
                          gridTemplateColumns: "minmax(7rem, 12rem) minmax(5rem, 1fr) 11rem",
                          gap: "0.75rem",
                          alignItems: "center",
                          fontSize: "0.88rem",
                        }}
                      >
                        <span>
                          {scope.work_type_name} ({scope.measure_symbol})
                        </span>
                        <ProgressMeter
                          percent={scope.percent}
                          status={scope.status}
                          label={`${project.name}, ${scope.work_type_name}: ${scope.percent}% done`}
                        />
                        <span style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                          <span style={{ fontVariantNumeric: "tabular-nums" }}>{scope.percent}%</span>
                          <StatusBadge status={scope.status} />
                        </span>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
          <div style={styles.card}>
            <h2>Not reported yet today</h2>
            {stats.missing.length === 0 ? (
              <p>Every team placed on an active project has reported today.</p>
            ) : (
              <ul>
                {stats.missing.map((row) => (
                  <li key={`${row.workplace}-${row.team}`}>
                    <Link to={`/reports?workplace=${row.workplace}`}>{row.workplace_name}</Link>: {row.team_number} ·{" "}
                    {row.team_name}
                    {row.lead_user_email ? ` (lead ${row.lead_user_email})` : ""}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div style={styles.card}>
            <h2>Running low</h2>
            {stats.low.length === 0 ? (
              <p>Nothing is below its reorder level.</p>
            ) : (
              <ul>
                {stats.low.map((row) => (
                  <li key={row.id}>
                    {row.item_name} at {row.location_name}: {row.on_hand} of {row.min_quantity} {row.unit}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div style={styles.card}>
            <h2>Expiring stock</h2>
            {stats.expiring.length === 0 ? (
              <p>No lots expire in the next 30 days.</p>
            ) : (
              <ul>
                {stats.expiring.map((lot) => (
                  <li key={lot.id}>
                    {lot.item_name} at {lot.location_name}: {lot.quantity} {lot.unit}, expires {lot.expires_on}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default DashboardPage;
