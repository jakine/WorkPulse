import { useCallback, useEffect, useState } from "react";
import { api, apiList } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { ErrorText, Field, companyToday, styles } from "./ui";

/** Record material used on a project's site, optionally against one of its work types. */
function MaterialUseForm({ workplaceId, date, onDone }) {
  const { user } = useAuth();
  const [lots, setLots] = useState(null);
  const [scopes, setScopes] = useState([]);
  const [form, setForm] = useState({
    lot: "",
    quantity: "",
    scope: "",
    happened_on: date || companyToday(user?.active_company),
    note: "",
  });
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [locations, scopeRows] = await Promise.all([
      apiList("/locations/"),
      apiList(`/project-scopes/?workplace=${workplaceId}`),
    ]);
    const site = locations.find((row) => row.workplace === Number(workplaceId));
    const lotRows = site ? await apiList(`/stock-lots/?location=${site.id}`) : [];
    setLots(lotRows.filter((lot) => Number(lot.quantity) > 0));
    setScopes(scopeRows);
  }, [workplaceId]);

  useEffect(() => {
    setError("");
    load().catch((err) => setError(err.message));
  }, [load]);

  useEffect(() => {
    if (date) setForm((current) => ({ ...current, happened_on: date }));
  }, [date]);

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/stock-movements/", {
        method: "POST",
        body: {
          lot: Number(form.lot),
          kind: "consume",
          quantity: form.quantity,
          workplace: Number(workplaceId),
          scope: form.scope ? Number(form.scope) : null,
          happened_on: form.happened_on,
          note: form.note,
        },
      });
      setForm((current) => ({ ...current, quantity: "", note: "" }));
      await load();
      if (onDone) await onDone();
    } catch (err) {
      setError(err.message);
    }
  }

  if (lots === null) return <ErrorText>{error}</ErrorText>;
  if (lots.length === 0) {
    return <p style={{ margin: 0, color: "var(--muted)" }}>No stock is on this site yet. Request material from the depot first.</p>;
  }

  const lot = lots.find((row) => String(row.id) === String(form.lot));
  return (
    <form onSubmit={submit} style={{ display: "grid", gap: "0.5rem" }}>
      <ErrorText>{error}</ErrorText>
      <div style={styles.row}>
        <Field label="Material">
          <select style={styles.input} value={form.lot} onChange={(e) => setForm({ ...form, lot: e.target.value })} required>
            <option value="">Choose</option>
            {lots.map((row) => (
              <option key={row.id} value={row.id}>
                {row.item_name} · {row.quantity} {row.unit} on site{row.expires_on ? ` · expires ${row.expires_on}` : ""}
              </option>
            ))}
          </select>
        </Field>
        <Field label={lot ? `Used (${lot.unit})` : "Used"}>
          <input
            style={styles.input}
            type="number"
            min="0.01"
            step="0.01"
            max={lot ? lot.quantity : undefined}
            value={form.quantity}
            onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            required
          />
        </Field>
        <Field label="For work type">
          <select style={styles.input} value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value })}>
            <option value="">Not linked</option>
            {scopes.map((scope) => (
              <option key={scope.id} value={scope.id}>
                {scope.work_type_name}
              </option>
            ))}
          </select>
        </Field>
        {!date && (
          <Field label="Day">
            <input
              style={styles.input}
              type="date"
              value={form.happened_on}
              onChange={(e) => setForm({ ...form, happened_on: e.target.value })}
              required
            />
          </Field>
        )}
        <Field label="Note">
          <input style={styles.input} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </Field>
        <button style={styles.button} type="submit">
          Record use
        </button>
      </div>
    </form>
  );
}

export default MaterialUseForm;
