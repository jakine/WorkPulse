import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiList } from "../api/client";
import { useRole } from "../context/AuthContext";
import MaterialUseForm from "./MaterialUseForm";
import { Badge, ErrorText, Field, formatDay, styles } from "./ui";

const REQUEST_COLORS = {
  open: "var(--warn)",
  partly_fulfilled: "var(--warn)",
  fulfilled: "var(--accent)",
  rejected: "var(--muted)",
};
const number = { ...styles.td, textAlign: "right", fontVariantNumeric: "tabular-nums" };
const numberHead = { ...styles.th, textAlign: "right" };

function difference(row) {
  const value = Number(row.variance);
  const sign = value > 0 ? "+" : "";
  const percent = row.variance_percent != null ? ` (${sign}${Math.round(Number(row.variance_percent))}%)` : "";
  return `${sign}${row.variance} ${row.unit}${percent}`;
}

function SiteMaterials({ place }) {
  const { canManage, isLead } = useRole();
  const canWrite = canManage || isLead;
  const [usage, setUsage] = useState(null);
  const [lots, setLots] = useState([]);
  const [requests, setRequests] = useState([]);
  const [items, setItems] = useState([]);
  const [lines, setLines] = useState([{ item: "", quantity: "" }]);
  const [details, setDetails] = useState({ needed_by: "", note: "" });
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [usageData, requestRows, itemRows] = await Promise.all([
      api(`/projects/${place.id}/materials/`),
      apiList(`/material-requests/?workplace=${place.id}`),
      apiList("/stock-items/"),
    ]);
    const lotRows = usageData.site_location ? await apiList(`/stock-lots/?location=${usageData.site_location}`) : [];
    setUsage(usageData);
    setLots(lotRows.filter((lot) => Number(lot.quantity) > 0));
    setRequests(requestRows);
    setItems(itemRows);
  }, [place.id]);

  useEffect(() => {
    setError("");
    load().catch((err) => setError(err.message));
  }, [load]);

  function setLine(index, key, value) {
    setLines((current) => current.map((line, at) => (at === index ? { ...line, [key]: value } : line)));
  }

  async function requestMaterial(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/material-requests/", {
        method: "POST",
        body: {
          workplace: place.id,
          needed_by: details.needed_by || null,
          note: details.note,
          lines: lines.map((line) => ({ item: Number(line.item), quantity: line.quantity })),
        },
      });
      setLines([{ item: "", quantity: "" }]);
      setDetails({ needed_by: "", note: "" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  if (!usage) return <ErrorText>{error || "Loading..."}</ErrorText>;

  const planned = usage.items.filter((row) => row.still_needed != null);
  const withNorms = usage.scopes.filter((scope) => scope.materials.length > 0);

  return (
    <div style={{ display: "grid", gap: "1.25rem" }}>
      <ErrorText>{error}</ErrorText>

      <div style={styles.card}>
        <div style={{ ...styles.row, justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0 }}>What the site still needs</h2>
          <Link to="/stock">Manage stock</Link>
        </div>
        {planned.length === 0 ? (
          <p style={{ marginBottom: 0 }}>
            Set how much material each work type uses on the Work types page to see what this site still needs.
          </p>
        ) : (
          <table style={{ ...styles.table, marginTop: "0.75rem" }}>
            <thead>
              <tr>
                <th style={styles.th}>Material</th>
                <th style={numberHead}>On site</th>
                <th style={numberHead}>Needed for the remaining work</th>
                <th style={numberHead}>Short</th>
              </tr>
            </thead>
            <tbody>
              {planned.map((row) => (
                <tr key={row.item}>
                  <td style={styles.td}>{row.item_name}</td>
                  <td style={number}>
                    {row.on_site} {row.unit}
                  </td>
                  <td style={number}>
                    {row.still_needed} {row.unit}
                  </td>
                  <td style={number}>
                    {Number(row.shortage) > 0 ? (
                      <Badge color="var(--warn)">
                        {row.shortage} {row.unit}
                      </Badge>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {withNorms.length > 0 && (
        <div style={styles.card}>
          <h2 style={{ marginTop: 0 }}>Material by work type</h2>
          <p style={{ marginTop: 0, color: "var(--muted)" }}>
            Expected use is the measured progress times the material each unit needs. A big difference points to waste or
            to use that was not recorded.
          </p>
          <div style={{ display: "grid", gap: "1rem" }}>
            {withNorms.map((scope) => (
              <div key={scope.scope} style={{ overflowX: "auto" }}>
                <h3 style={{ margin: "0 0 0.4rem" }}>
                  {scope.work_type_name} · {scope.done} {scope.measure_symbol} done
                </h3>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>Material</th>
                      <th style={numberHead}>Per {scope.measure_symbol}</th>
                      <th style={numberHead}>Expected</th>
                      <th style={numberHead}>Used</th>
                      <th style={numberHead}>Difference</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scope.materials.map((row) => (
                      <tr key={row.item}>
                        <td style={styles.td}>{row.item_name}</td>
                        <td style={number}>
                          {row.per_unit} {row.unit}
                        </td>
                        <td style={number}>
                          {row.expected} {row.unit}
                        </td>
                        <td style={number}>
                          {row.actual} {row.unit}
                        </td>
                        <td style={number}>{difference(row)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
          {usage.unassigned_use.length > 0 && (
            <p style={{ marginBottom: 0, color: "var(--muted)" }}>
              Used without a work type:{" "}
              {usage.unassigned_use.map((row) => `${row.item_name} ${row.quantity} ${row.unit}`).join(", ")}
            </p>
          )}
        </div>
      )}

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>On site now</h2>
        {lots.length === 0 ? (
          <p style={{ margin: 0 }}>No stock is on this site yet.</p>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Material</th>
                <th style={numberHead}>Quantity</th>
                <th style={styles.th}>Expires</th>
              </tr>
            </thead>
            <tbody>
              {lots.map((lot) => (
                <tr key={lot.id}>
                  <td style={styles.td}>{lot.item_name}</td>
                  <td style={number}>
                    {lot.quantity} {lot.unit}
                  </td>
                  <td style={styles.td}>{lot.expires_on ? formatDay(lot.expires_on) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {canWrite && (
        <div style={styles.card}>
          <h2 style={{ marginTop: 0 }}>Record material used</h2>
          <MaterialUseForm workplaceId={place.id} onDone={load} />
        </div>
      )}

      <div style={styles.card}>
        <h2 style={{ marginTop: 0 }}>Material requests</h2>
        {requests.length === 0 ? (
          <p style={{ marginTop: 0 }}>No requests from this site yet.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: "0 0 1rem", display: "grid", gap: "0.6rem" }}>
            {requests.map((row) => (
              <li key={row.id} style={{ background: "var(--surface-2)", borderRadius: "var(--radius-sm)", padding: "0.6rem 0.8rem" }}>
                <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
                  <strong>#{row.id}</strong>
                  <Badge color={REQUEST_COLORS[row.status]}>{row.status_label}</Badge>
                  <span style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                    {row.requested_by_email}
                    {row.needed_by ? ` · needed by ${formatDay(row.needed_by)}` : ""}
                  </span>
                </div>
                <div style={{ fontSize: "0.9rem", marginTop: "0.25rem" }}>
                  {row.lines
                    .map((line) => `${line.item_name}: ${line.fulfilled_quantity} of ${line.quantity} ${line.unit} sent`)
                    .join(" · ")}
                </div>
                {row.note && <div style={{ fontSize: "0.85rem", color: "var(--muted)" }}>{row.note}</div>}
                {row.decision_note && <div style={{ fontSize: "0.85rem", color: "var(--muted)" }}>Office: {row.decision_note}</div>}
              </li>
            ))}
          </ul>
        )}
        {canWrite && (
          <form onSubmit={requestMaterial} style={{ display: "grid", gap: "0.6rem" }}>
            <h3 style={{ margin: 0 }}>Request material from the depot</h3>
            {lines.map((line, index) => {
              const item = items.find((row) => String(row.id) === String(line.item));
              return (
                <div key={index} style={styles.row}>
                  <Field label="Material">
                    <select style={styles.input} value={line.item} onChange={(e) => setLine(index, "item", e.target.value)} required>
                      <option value="">Choose</option>
                      {items.map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.name}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label={item ? `Quantity (${item.unit})` : "Quantity"}>
                    <input
                      style={styles.input}
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={line.quantity}
                      onChange={(e) => setLine(index, "quantity", e.target.value)}
                      required
                    />
                  </Field>
                  {lines.length > 1 && (
                    <button type="button" style={styles.quiet} onClick={() => setLines(lines.filter((_, at) => at !== index))}>
                      Remove
                    </button>
                  )}
                </div>
              );
            })}
            <div style={styles.row}>
              <button type="button" style={styles.quiet} onClick={() => setLines([...lines, { item: "", quantity: "" }])}>
                Add another material
              </button>
            </div>
            <div style={styles.row}>
              <Field label="Needed by">
                <input
                  style={styles.input}
                  type="date"
                  value={details.needed_by}
                  onChange={(e) => setDetails({ ...details, needed_by: e.target.value })}
                />
              </Field>
              <Field label="Note">
                <input style={styles.input} value={details.note} onChange={(e) => setDetails({ ...details, note: e.target.value })} />
              </Field>
              <button style={styles.button} type="submit">
                Send request
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

export default SiteMaterials;
