import { useEffect, useMemo, useState } from "react";
import { api, apiList } from "../api/client";
import { getMe } from "../api/auth";
import { useAuth, useRole } from "../context/AuthContext";
import { ErrorText, Field, styles } from "../components/ui";

function timeZoneOptions(current) {
  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
  return Array.from(new Set(["UTC", current, ...zones].filter(Boolean)));
}

function CompanyPage() {
  const { user, setUser } = useAuth();
  const { canManage } = useRole();
  const [settings, setSettings] = useState({ name: "", timezone: "UTC" });
  const [saved, setSaved] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteRole, setInviteRole] = useState("manager");
  const [inviteTeam, setInviteTeam] = useState("");
  const [teams, setTeams] = useState([]);
  const [members, setMembers] = useState([]);
  const [error, setError] = useState("");

  const company = user?.active_company;
  const zones = useMemo(() => timeZoneOptions(company?.timezone), [company?.timezone]);

  useEffect(() => {
    if (!company) return;
    setSettings({ name: company.name, timezone: company.timezone || "UTC" });
    setSaved("");
  }, [company]);

  async function refreshUser() {
    setUser(await getMe());
  }

  useEffect(() => {
    if (!company) {
      setMembers([]);
      return;
    }
    apiList("/companies/members/")
      .then(setMembers)
      .catch((err) => setError(err.message));
    if (company.role === "owner") {
      apiList("/teams/")
        .then(setTeams)
        .catch((err) => setError(err.message));
    }
  }, [company]);

  async function createCompany(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/companies/", { method: "POST", body: { name } });
      setName("");
      await refreshUser();
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveSettings(event) {
    event.preventDefault();
    setError("");
    setSaved("");
    try {
      await api("/companies/current/", { method: "PATCH", body: settings });
      await refreshUser();
      setSaved("Saved.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function switchCompany(companyId) {
    setError("");
    try {
      await api("/companies/switch/", { method: "POST", body: { company_id: companyId } });
      await refreshUser();
    } catch (err) {
      setError(err.message);
    }
  }

  async function invite(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/companies/members/", {
        method: "POST",
        body: {
          email,
          password,
          role: inviteRole,
          team: inviteRole === "team_lead" && inviteTeam ? Number(inviteTeam) : null,
        },
      });
      setEmail("");
      setPassword("");
      setInviteTeam("");
      setMembers(await apiList("/companies/members/"));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={styles.page}>
      <h1 style={{ margin: 0 }}>Company</h1>
      <ErrorText>{error}</ErrorText>

      <form onSubmit={createCompany} style={styles.card}>
        <h2 style={{ marginTop: 0 }}>New company</h2>
        <div style={styles.row}>
          <Field label="Name">
            <input style={styles.input} value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <button style={styles.button} type="submit">
            Create
          </button>
        </div>
      </form>

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Your companies</h2>
        {(user?.companies || []).length === 0 ? (
          <p>You do not belong to a company yet.</p>
        ) : (
          <ul>
            {(user.companies || []).map((item) => (
              <li key={item.id} style={{ marginBottom: "0.5rem" }}>
                {item.name} ({item.role})
                {company?.id !== item.id && (
                  <button style={{ ...styles.quiet, marginLeft: "0.75rem" }} type="button" onClick={() => switchCompany(item.id)}>
                    Switch
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {company && canManage && (
        <form onSubmit={saveSettings} style={styles.card}>
          <h2 style={{ marginTop: 0 }}>Company settings</h2>
          <p style={{ marginTop: 0 }}>The time zone decides which day counts as today for reports and stock.</p>
          <div style={styles.row}>
            <Field label="Name">
              <input
                style={styles.input}
                value={settings.name}
                onChange={(e) => setSettings((current) => ({ ...current, name: e.target.value }))}
                required
              />
            </Field>
            <Field label="Time zone">
              <select
                style={styles.input}
                value={settings.timezone}
                onChange={(e) => setSettings((current) => ({ ...current, timezone: e.target.value }))}
              >
                {zones.map((zone) => (
                  <option key={zone} value={zone}>
                    {zone}
                  </option>
                ))}
              </select>
            </Field>
            <button style={styles.button} type="submit">
              Save
            </button>
            {saved && <span style={{ color: "var(--muted)" }}>{saved}</span>}
          </div>
        </form>
      )}

      {company?.role === "owner" && (
        <form onSubmit={invite} style={styles.card}>
          <h2 style={{ marginTop: 0 }}>Invite someone</h2>
          <p style={{ marginTop: 0 }}>
            Managers run everything. Team leads see the projects their teams work on, fill reports, and move their team's tasks.
          </p>
          <div style={styles.row}>
            <Field label="Email">
              <input style={styles.input} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </Field>
            <Field label="Password for a new account">
              <input style={styles.input} type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <Field label="Role">
              <select style={styles.input} value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}>
                <option value="manager">Manager</option>
                <option value="team_lead">Team lead</option>
              </select>
            </Field>
            {inviteRole === "team_lead" && (
              <Field label="Leads team">
                <select style={styles.input} value={inviteTeam} onChange={(e) => setInviteTeam(e.target.value)}>
                  <option value="">Link later</option>
                  {teams.map((team) => (
                    <option key={team.id} value={team.id}>
                      {team.number} · {team.name}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            <button style={styles.button} type="submit">
              Invite
            </button>
          </div>
        </form>
      )}

      {company && (
        <div style={styles.card}>
          <h2 style={{ marginTop: 0 }}>People</h2>
          <ul>
            {members.map((member) => (
              <li key={member.id}>
                {member.email} · {member.role === "team_lead" ? "team lead" : member.role}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default CompanyPage;
