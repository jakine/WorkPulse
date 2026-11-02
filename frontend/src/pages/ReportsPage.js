import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { apiList } from "../api/client";
import DailyReports from "../components/DailyReports";
import { ErrorText, Field, PageHeader, styles } from "../components/ui";

function ReportsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [places, setPlaces] = useState([]);
  const workplaceId = searchParams.get("workplace") || "";
  const [error, setError] = useState("");

  useEffect(() => {
    apiList("/projects/")
      .then(setPlaces)
      .catch((err) => setError(err.message));
  }, []);

  function chooseProject(id) {
    if (id) setSearchParams({ workplace: id });
    else setSearchParams({});
  }

  return (
    <div style={styles.page}>
      <PageHeader title="Daily log">
        Pick a project and a day: who was on site, what got done, issues, photos and notes. A manager approves the day
        when it is complete.
      </PageHeader>
      <ErrorText>{error}</ErrorText>
      <div style={styles.card}>
        <div style={styles.row}>
          <Field label="Project">
            <select style={styles.input} value={workplaceId} onChange={(e) => chooseProject(e.target.value)}>
              <option value="">Choose</option>
              {places.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </Field>
          {workplaceId && (
            <Link to={`/projects/${workplaceId}?tab=sheet`} style={{ alignSelf: "end", marginBottom: "0.55rem" }}>
              Open sheet
            </Link>
          )}
        </div>
      </div>
      {workplaceId && <DailyReports workplaceId={workplaceId} />}
    </div>
  );
}

export default ReportsPage;
