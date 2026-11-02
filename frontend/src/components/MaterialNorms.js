import { useCallback, useEffect, useState } from "react";
import { api, apiList } from "../api/client";
import { ErrorText, Field, WorkTypeOptions, styles } from "./ui";

/** How much material one unit of each work type uses, e.g. 1.4 kg adhesive per m² of facade. */
function MaterialNorms() {
  const [norms, setNorms] = useState([]);
  const [workTypes, setWorkTypes] = useState([]);
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ work_type: "", item: "", quantity_per_unit: "" });
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [normRows, typeRows, itemRows] = await Promise.all([
      apiList("/work-type-materials/"),
      apiList("/work-types/"),
      apiList("/stock-items/"),
    ]);
    setNorms(normRows);
    setWorkTypes(typeRows);
    setItems(itemRows);
  }, []);

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [load]);

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
      await api("/work-type-materials/", {
        method: "POST",
        body: { work_type: Number(form.work_type), item: Number(form.item), quantity_per_unit: form.quantity_per_unit },
      });
      setForm({ work_type: form.work_type, item: "", quantity_per_unit: "" });
    });
  }

  const workType = workTypes.find((row) => String(row.id) === String(form.work_type));
  const item = items.find((row) => String(row.id) === String(form.item));
  return (
    <div style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Material per unit of work</h2>
      <p style={{ marginTop: 0 }}>
        Say how much material one unit of a work type uses. Projects then show the material they should have used and
        what they still need.
      </p>
      <ErrorText>{error}</ErrorText>
      {items.length === 0 ? (
        <p>Add stock items on the Stock page first.</p>
      ) : (
        <form onSubmit={save} style={{ ...styles.row, marginBottom: "0.75rem" }}>
          <Field label="Work type">
            <select style={styles.input} value={form.work_type} onChange={(e) => setForm({ ...form, work_type: e.target.value })} required>
              <option value="">Choose</option>
              <WorkTypeOptions types={workTypes} />
            </select>
          </Field>
          <Field label="Material">
            <select style={styles.input} value={form.item} onChange={(e) => setForm({ ...form, item: e.target.value })} required>
              <option value="">Choose</option>
              {items.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name} ({row.unit})
                </option>
              ))}
            </select>
          </Field>
          <Field label={item && workType ? `${item.unit} per ${workType.measure_symbol}` : "Amount per unit"}>
            <input
              style={styles.input}
              type="number"
              min="0.0001"
              step="0.0001"
              value={form.quantity_per_unit}
              onChange={(e) => setForm({ ...form, quantity_per_unit: e.target.value })}
              required
            />
          </Field>
          <button style={styles.button} type="submit">
            Add
          </button>
        </form>
      )}
      {norms.length > 0 && (
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Work type</th>
              <th style={styles.th}>Material</th>
              <th style={{ ...styles.th, textAlign: "right" }}>Per unit</th>
              <th style={styles.th}></th>
            </tr>
          </thead>
          <tbody>
            {norms.map((norm) => (
              <tr key={norm.id}>
                <td style={styles.td}>{norm.work_type_name}</td>
                <td style={styles.td}>{norm.item_name}</td>
                <td style={{ ...styles.td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                  {Number(norm.quantity_per_unit)} {norm.unit} per {norm.measure_symbol}
                </td>
                <td style={styles.td}>
                  <button
                    type="button"
                    style={styles.danger}
                    onClick={() => run(() => api(`/work-type-materials/${norm.id}/`, { method: "DELETE" }))}
                  >
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

export default MaterialNorms;
