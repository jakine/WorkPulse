import { useCallback, useEffect, useState } from "react";
import { api, apiList } from "../api/client";
import { ErrorText, Field, styles } from "./ui";

/** Reorder levels: warn when an item at a depot or site drops below its minimum. */
function StockLevels({ items, locations, version }) {
  const [levels, setLevels] = useState([]);
  const [low, setLow] = useState([]);
  const [form, setForm] = useState({ item: "", location: "", min_quantity: "" });
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [levelRows, lowRows] = await Promise.all([apiList("/stock-levels/"), api("/stock-levels/low/")]);
    setLevels(levelRows);
    setLow(lowRows);
  }, []);

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [load, version]);

  async function run(action) {
    setError("");
    try {
      await action();
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  function save(event) {
    event.preventDefault();
    run(async () => {
      await api("/stock-levels/", {
        method: "POST",
        body: { item: Number(form.item), location: Number(form.location), min_quantity: form.min_quantity },
      });
      setForm({ item: "", location: "", min_quantity: "" });
    });
  }

  const lowIds = new Set(low.map((row) => row.id));
  return (
    <div style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Reorder levels</h2>
      <ErrorText>{error}</ErrorText>
      {low.length > 0 && (
        <p style={{ marginTop: 0 }} role="status">
          <strong style={{ color: "var(--warn)" }}>Running low:</strong>{" "}
          {low.map((row) => `${row.item_name} at ${row.location_name} (${row.on_hand} of ${row.min_quantity} ${row.unit})`).join(", ")}
        </p>
      )}
      <form onSubmit={save} style={{ ...styles.row, marginBottom: "0.75rem" }}>
        <Field label="Material">
          <select style={styles.input} value={form.item} onChange={(e) => setForm({ ...form, item: e.target.value })} required>
            <option value="">Choose</option>
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="At">
          <select style={styles.input} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} required>
            <option value="">Choose</option>
            {locations.map((location) => (
              <option key={location.id} value={location.id}>
                {location.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Warn below">
          <input
            style={styles.input}
            type="number"
            min="0"
            step="0.01"
            value={form.min_quantity}
            onChange={(e) => setForm({ ...form, min_quantity: e.target.value })}
            required
          />
        </Field>
        <button style={styles.button} type="submit">
          Set level
        </button>
      </form>
      {levels.length > 0 && (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Material</th>
              <th style={styles.th}>At</th>
              <th style={{ ...styles.th, textAlign: "right" }}>Warn below</th>
              <th style={styles.th}></th>
            </tr>
          </thead>
          <tbody>
            {levels.map((level) => (
              <tr key={level.id}>
                <td style={styles.td}>
                  {level.item_name}
                  {lowIds.has(level.id) && <strong style={{ color: "var(--warn)" }}> · low</strong>}
                </td>
                <td style={styles.td}>{level.location_name}</td>
                <td style={{ ...styles.td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  {level.min_quantity} {level.unit}
                </td>
                <td style={styles.td}>
                  <button type="button" style={styles.danger} onClick={() => run(() => api(`/stock-levels/${level.id}/`, { method: "DELETE" }))}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default StockLevels;
