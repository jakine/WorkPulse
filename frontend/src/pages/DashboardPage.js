import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ProgressMeter, StatusBadge } from "../components/charts";
import { ErrorText, PageHeader, formatDay, styles } from "../components/ui";
import { useAuth } from "../context/AuthContext";

function DashboardPage() {
  const { user } = useAuth();
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
