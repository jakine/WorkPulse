import { useEffect, useState } from "react";
import { api, apiList } from "../api/client";
import MaterialNorms from "../components/MaterialNorms";
import { ErrorText, Field, styles } from "../components/ui";
import { useRole } from "../context/AuthContext";

const emptyKind = { name: "" };
const emptyMeasure = { name: "", symbol: "", kind: "" };
const emptyCategory = { name: "" };
const emptyType = { name: "", category: "", measure: "" };
const emptyDuration = { name: "", symbol: "", days_per_unit: "1", timeline_step: "" };

function WorkTypesPage() {
  const { canManage } = useRole();
  const [kinds, setKinds] = useState([]);
  const [categories, setCategories] = useState([]);
  const [measures, setMeasures] = useState([]);
  const [types, setTypes] = useState([]);
  const [durations, setDurations] = useState([]);
  const [kindForm, setKindForm] = useState(emptyKind);
  const [categoryForm, setCategoryForm] = useState(emptyCategory);
  const [measureForm, setMeasureForm] = useState(emptyMeasure);
  const [typeForm, setTypeForm] = useState(emptyType);
  const [durationForm, setDurationForm] = useState(emptyDuration);
  const [editingKindId, setEditingKindId] = useState(null);
  const [editingCategoryId, setEditingCategoryId] = useState(null);
  const [editingMeasureId, setEditingMeasureId] = useState(null);
  const [editingTypeId, setEditingTypeId] = useState(null);
  const [editingDurationId, setEditingDurationId] = useState(null);
  const [error, setError] = useState("");

  async function load() {
    const [kindRows, categoryRows, measureRows, typeRows, durationRows] = await Promise.all([
      apiList("/work-kinds/"),
      apiList("/work-type-categories/"),
      apiList("/work-measures/"),
      apiList("/work-types/"),
      apiList("/duration-units/"),
    ]);
    setKinds(kindRows);
    setCategories(categoryRows);
    setMeasures(measureRows);
    setTypes(typeRows);
    setDurations(durationRows);
    setMeasureForm((current) =>
      current.kind || kindRows.length === 0 ? current : { ...current, kind: String(kindRows[0].id) }
    );
    setTypeForm((current) => ({
      ...current,
      category: current.category || (categoryRows[0] ? String(categoryRows[0].id) : ""),
      measure: current.measure || (measureRows[0] ? String(measureRows[0].id) : ""),
    }));
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function saveKind(event) {
    event.preventDefault();
    setError("");
    try {
      if (editingKindId) {
        await api(`/work-kinds/${editingKindId}/`, { method: "PATCH", body: kindForm });
      } else {
        await api("/work-kinds/", { method: "POST", body: { ...kindForm, position: kinds.length } });
      }
      setKindForm(emptyKind);
      setEditingKindId(null);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveMeasure(event) {
    event.preventDefault();
    setError("");
    try {
      const body = { name: measureForm.name, symbol: measureForm.symbol, kind: Number(measureForm.kind) };
      if (editingMeasureId) {
        await api(`/work-measures/${editingMeasureId}/`, { method: "PATCH", body });
      } else {
        await api("/work-measures/", { method: "POST", body });
      }
      setMeasureForm({ name: "", symbol: "", kind: measureForm.kind });
      setEditingMeasureId(null);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveCategory(event) {
    event.preventDefault();
    setError("");
    try {
      if (editingCategoryId) {
        await api(`/work-type-categories/${editingCategoryId}/`, { method: "PATCH", body: categoryForm });
      } else {
        await api("/work-type-categories/", {
          method: "POST",
          body: { ...categoryForm, position: categories.length },
        });
      }
      setCategoryForm(emptyCategory);
      setEditingCategoryId(null);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveDuration(event) {
    event.preventDefault();
    setError("");
    try {
      const body = {
        name: durationForm.name,
        symbol: durationForm.symbol,
        days_per_unit: durationForm.days_per_unit,
        timeline_step: durationForm.timeline_step,
      };
      if (editingDurationId) {
        await api(`/duration-units/${editingDurationId}/`, { method: "PATCH", body });
      } else {
        await api("/duration-units/", { method: "POST", body: { ...body, position: durations.length } });
      }
      setDurationForm(emptyDuration);
      setEditingDurationId(null);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveType(event) {
    event.preventDefault();
    setError("");
    try {
      const body = {
        name: typeForm.name,
        category: Number(typeForm.category),
        measure: Number(typeForm.measure),
      };
      if (editingTypeId) {
        await api(`/work-types/${editingTypeId}/`, { method: "PATCH", body });
      } else {
        await api("/work-types/", { method: "POST", body });
      }
      setTypeForm({ name: "", category: typeForm.category, measure: typeForm.measure });
      setEditingTypeId(null);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function reorderKinds(ids) {
    setError("");
    try {
      setKinds(await api("/work-kinds/reorder/", { method: "POST", body: { ids } }));
    } catch (err) {
      setError(err.message);
      await load().catch((loadErr) => setError(loadErr.message));
    }
  }

  async function reorderDurations(ids) {
    setError("");
    try {
      setDurations(await api("/duration-units/reorder/", { method: "POST", body: { ids } }));
    } catch (err) {
      setError(err.message);
      await load().catch((loadErr) => setError(loadErr.message));
    }
  }

  async function reorderCategories(ids) {
    setError("");
    try {
      setCategories(await api("/work-type-categories/reorder/", { method: "POST", body: { ids } }));
    } catch (err) {
      setError(err.message);
      await load().catch((loadErr) => setError(loadErr.message));
    }
  }

  function moveKind(index, offset) {
    const next = index + offset;
    if (next < 0 || next >= kinds.length) return;
    const ids = kinds.map((kind) => kind.id);
    const [moved] = ids.splice(index, 1);
    ids.splice(next, 0, moved);
    setKinds(ids.map((id, position) => ({ ...kinds.find((kind) => kind.id === id), position })));
    reorderKinds(ids);
  }

  function moveDuration(index, offset) {
    const next = index + offset;
    if (next < 0 || next >= durations.length) return;
    const ids = durations.map((unit) => unit.id);
    const [moved] = ids.splice(index, 1);
    ids.splice(next, 0, moved);
    setDurations(ids.map((id, position) => ({ ...durations.find((unit) => unit.id === id), position })));
    reorderDurations(ids);
  }

  function moveCategory(index, offset) {
    const next = index + offset;
    if (next < 0 || next >= categories.length) return;
    const ids = categories.map((category) => category.id);
    const [moved] = ids.splice(index, 1);
    ids.splice(next, 0, moved);
    setCategories(ids.map((id, position) => ({ ...categories.find((category) => category.id === id), position })));
    reorderCategories(ids);
  }

  async function remove(path, row, label) {
    if (!window.confirm(`Delete ${label} “${row.name}”? Records still using it cannot be deleted this way.`)) return;
    setError("");
    try {
      await api(`${path}${row.id}/`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={styles.page}>
      <h1 style={{ margin: 0 }}>Work types</h1>
      <p style={{ margin: 0 }}>
        A kind groups measures, such as area or volume. A work type category groups types used on projects, such as
        finishes or structure. A work type such as facade sits in one category and uses one measure. Duration units
        convert project length and the timeline scale into days.
      </p>
      <ErrorText>{error}</ErrorText>

      {canManage && (
        <>
          <form onSubmit={saveKind} style={styles.card}>
            <h2 style={{ marginTop: 0 }}>{editingKindId ? "Edit kind" : "Add kind"}</h2>
            <div style={styles.row}>
              <Field label="Name">
                <input
                  style={styles.input}
                  value={kindForm.name}
                  onChange={(e) => setKindForm({ name: e.target.value })}
                  placeholder="Area"
                  required
                />
              </Field>
              <button style={styles.button} type="submit">
                {editingKindId ? "Save" : "Add kind"}
              </button>
              {editingKindId && (
                <button
                  type="button"
                  style={styles.quiet}
                  onClick={() => {
                    setEditingKindId(null);
                    setKindForm(emptyKind);
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
          </form>

          <div style={styles.card}>
            {kinds.length === 0 ? (
              <p>No kinds yet.</p>
            ) : (
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Order</th>
                    <th style={styles.th}>Kind</th>
                    <th style={styles.th}></th>
                  </tr>
                </thead>
                <tbody>
                  {kinds.map((kind, index) => (
                    <tr key={kind.id}>
                      <td style={styles.td}>
                        <button type="button" style={styles.quiet} onClick={() => moveKind(index, -1)} disabled={index === 0}>
                          Up
                        </button>{" "}
                        <button
                          type="button"
                          style={styles.quiet}
                          onClick={() => moveKind(index, 1)}
                          disabled={index === kinds.length - 1}
                        >
                          Down
                        </button>
                      </td>
                      <td style={styles.td}>{kind.name}</td>
                      <td style={styles.td}>
                        <button
                          type="button"
                          style={styles.button}
                          onClick={() => {
                            setEditingKindId(kind.id);
                            setKindForm({ name: kind.name });
                          }}
                        >
                          Edit
                        </button>{" "}
                        <button type="button" style={styles.danger} onClick={() => remove("/work-kinds/", kind, "kind")}>
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <form onSubmit={saveDuration} style={styles.card}>
            <h2 style={{ marginTop: 0 }}>{editingDurationId ? "Edit duration unit" : "Add duration unit"}</h2>
            <div style={styles.row}>
              <Field label="Name">
                <input
                  style={styles.input}
                  value={durationForm.name}
                  onChange={(e) => setDurationForm({ ...durationForm, name: e.target.value })}
                  placeholder="Fortnight"
                  required
                />
              </Field>
              <Field label="Symbol">
                <input
                  style={styles.input}
                  value={durationForm.symbol}
                  onChange={(e) => setDurationForm({ ...durationForm, symbol: e.target.value })}
                  placeholder="fn"
                  required
                />
              </Field>
              <Field label="Days per unit">
                <input
                  style={styles.input}
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={durationForm.days_per_unit}
                  onChange={(e) => setDurationForm({ ...durationForm, days_per_unit: e.target.value })}
                  required
                />
              </Field>
              <Field label="Timeline">
                <select
                  style={styles.input}
                  value={durationForm.timeline_step}
                  onChange={(e) => setDurationForm({ ...durationForm, timeline_step: e.target.value })}
                >
                  <option value="">Length only</option>
                  <option value="day">Days</option>
                  <option value="week">Weeks</option>
                  <option value="month">Months</option>
                </select>
              </Field>
              <button style={styles.button} type="submit">
                {editingDurationId ? "Save" : "Add unit"}
              </button>
              {editingDurationId && (
                <button
                  type="button"
                  style={styles.quiet}
                  onClick={() => {
                    setEditingDurationId(null);
                    setDurationForm(emptyDuration);
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
          </form>
        </>
      )}

      <div style={styles.card}>
        {durations.length === 0 ? (
          <p>No duration units yet.</p>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                {canManage && <th style={styles.th}>Order</th>}
                <th style={styles.th}>Unit</th>
                <th style={styles.th}>Symbol</th>
                <th style={styles.th}>Days</th>
                <th style={styles.th}>Timeline</th>
                {canManage && <th style={styles.th}></th>}
              </tr>
            </thead>
            <tbody>
              {durations.map((unit, index) => (
                <tr key={unit.id}>
                  {canManage && (
                    <td style={styles.td}>
                      <button type="button" style={styles.quiet} onClick={() => moveDuration(index, -1)} disabled={index === 0}>
                        Up
                      </button>{" "}
                      <button
                        type="button"
                        style={styles.quiet}
                        onClick={() => moveDuration(index, 1)}
                        disabled={index === durations.length - 1}
                      >
                        Down
                      </button>
                    </td>
                  )}
                  <td style={styles.td}>{unit.name}</td>
                  <td style={styles.td}>{unit.symbol}</td>
                  <td style={styles.td}>{unit.days_per_unit}</td>
                  <td style={styles.td}>{unit.timeline_step || "—"}</td>
                  {canManage && (
                    <td style={styles.td}>
                      <button
                        type="button"
                        style={styles.button}
                        onClick={() => {
                          setEditingDurationId(unit.id);
                          setDurationForm({
                            name: unit.name,
                            symbol: unit.symbol,
                            days_per_unit: unit.days_per_unit,
                            timeline_step: unit.timeline_step || "",
                          });
                        }}
                      >
                        Edit
                      </button>{" "}
                      <button
                        type="button"
                        style={styles.danger}
                        onClick={() => remove("/duration-units/", unit, "duration unit")}
                      >
                        Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {canManage && (
        <>
          <form onSubmit={saveMeasure} style={styles.card}>
            <h2 style={{ marginTop: 0 }}>{editingMeasureId ? "Edit measure" : "Add measure"}</h2>
            <div style={styles.row}>
              <Field label="Name">
                <input
                  style={styles.input}
                  value={measureForm.name}
                  onChange={(e) => setMeasureForm({ ...measureForm, name: e.target.value })}
                  placeholder="Square meters"
                  required
                />
              </Field>
              <Field label="Symbol">
                <input
                  style={styles.input}
                  value={measureForm.symbol}
                  onChange={(e) => setMeasureForm({ ...measureForm, symbol: e.target.value })}
                  placeholder="m²"
                  required
                />
              </Field>
              <Field label="Kind">
                <select
                  style={styles.input}
                  value={measureForm.kind}
                  onChange={(e) => setMeasureForm({ ...measureForm, kind: e.target.value })}
                  required
                >
                  <option value="">Choose</option>
                  {kinds.map((kind) => (
                    <option key={kind.id} value={kind.id}>
                      {kind.name}
                    </option>
                  ))}
                </select>
              </Field>
              <button style={styles.button} type="submit">
                {editingMeasureId ? "Save" : "Add measure"}
              </button>
              {editingMeasureId && (
                <button
                  type="button"
                  style={styles.quiet}
                  onClick={() => {
                    setEditingMeasureId(null);
                    setMeasureForm({ name: "", symbol: "", kind: kinds[0] ? String(kinds[0].id) : "" });
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
          </form>
        </>
      )}

      <div style={styles.card}>
        {measures.length === 0 ? (
          <p>No measures yet.</p>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Name</th>
                <th style={styles.th}>Symbol</th>
                <th style={styles.th}>Kind</th>
                {canManage && <th style={styles.th}></th>}
              </tr>
            </thead>
            <tbody>
              {measures.map((measure) => (
                <tr key={measure.id}>
                  <td style={styles.td}>{measure.name}</td>
                  <td style={styles.td}>{measure.symbol}</td>
                  <td style={styles.td}>{measure.kind_name}</td>
                  {canManage && (
                    <td style={styles.td}>
                      <button
                        type="button"
                        style={styles.button}
                        onClick={() => {
                          setEditingMeasureId(measure.id);
                          setMeasureForm({
                            name: measure.name,
                            symbol: measure.symbol,
                            kind: String(measure.kind),
                          });
                        }}
                      >
                        Edit
                      </button>{" "}
                      <button type="button" style={styles.danger} onClick={() => remove("/work-measures/", measure, "measure")}>
                        Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {canManage && (
        <form onSubmit={saveCategory} style={styles.card}>
          <h2 style={{ marginTop: 0 }}>{editingCategoryId ? "Edit category" : "Add category"}</h2>
          <div style={styles.row}>
            <Field label="Name">
              <input
                style={styles.input}
                value={categoryForm.name}
                onChange={(e) => setCategoryForm({ name: e.target.value })}
                placeholder="Finishes"
                required
              />
            </Field>
            <button style={styles.button} type="submit">
              {editingCategoryId ? "Save" : "Add category"}
            </button>
            {editingCategoryId && (
              <button
                type="button"
                style={styles.quiet}
                onClick={() => {
                  setEditingCategoryId(null);
                  setCategoryForm(emptyCategory);
                }}
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      )}

      <div style={styles.card}>
        {categories.length === 0 ? (
          <p>No categories yet.</p>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                {canManage && <th style={styles.th}>Order</th>}
                <th style={styles.th}>Category</th>
                {canManage && <th style={styles.th}></th>}
              </tr>
            </thead>
            <tbody>
              {categories.map((category, index) => (
                <tr key={category.id}>
                  {canManage && (
                    <td style={styles.td}>
                      <button type="button" style={styles.quiet} onClick={() => moveCategory(index, -1)} disabled={index === 0}>
                        Up
                      </button>{" "}
                      <button
                        type="button"
                        style={styles.quiet}
                        onClick={() => moveCategory(index, 1)}
                        disabled={index === categories.length - 1}
                      >
                        Down
                      </button>
                    </td>
                  )}
                  <td style={styles.td}>{category.name}</td>
                  {canManage && (
                    <td style={styles.td}>
                      <button
                        type="button"
                        style={styles.button}
                        onClick={() => {
                          setEditingCategoryId(category.id);
                          setCategoryForm({ name: category.name });
                        }}
                      >
                        Edit
                      </button>{" "}
                      <button
                        type="button"
                        style={styles.danger}
                        onClick={() => remove("/work-type-categories/", category, "category")}
                      >
                        Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {canManage && (
        <form onSubmit={saveType} style={styles.card}>
          <h2 style={{ marginTop: 0 }}>{editingTypeId ? "Edit work type" : "Add work type"}</h2>
          <div style={styles.row}>
            <Field label="Name">
              <input
                style={styles.input}
                value={typeForm.name}
                onChange={(e) => setTypeForm({ ...typeForm, name: e.target.value })}
                placeholder="Facade"
                required
              />
            </Field>
            <Field label="Category">
              <select
                style={styles.input}
                value={typeForm.category}
                onChange={(e) => setTypeForm({ ...typeForm, category: e.target.value })}
                required
              >
                <option value="">Choose</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Measure">
              <select
                style={styles.input}
                value={typeForm.measure}
                onChange={(e) => setTypeForm({ ...typeForm, measure: e.target.value })}
                required
              >
                <option value="">Choose</option>
                {measures.map((measure) => (
                  <option key={measure.id} value={measure.id}>
                    {measure.name} ({measure.symbol})
                  </option>
                ))}
              </select>
            </Field>
            <button style={styles.button} type="submit">
              {editingTypeId ? "Save" : "Add type"}
            </button>
            {editingTypeId && (
              <button
                type="button"
                style={styles.quiet}
                onClick={() => {
                  setEditingTypeId(null);
                  setTypeForm({
                    name: "",
                    category: categories[0] ? String(categories[0].id) : "",
                    measure: measures[0] ? String(measures[0].id) : "",
                  });
                }}
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      )}

      <div style={styles.card}>
        {types.length === 0 ? (
          <p>No work types yet. Add a category and a measure first, then a type such as facade or excavation.</p>
        ) : (
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Work type</th>
                <th style={styles.th}>Category</th>
                <th style={styles.th}>Measure</th>
                <th style={styles.th}>Kind</th>
                {canManage && <th style={styles.th}></th>}
              </tr>
            </thead>
            <tbody>
              {types.map((type) => (
                <tr key={type.id}>
                  <td style={styles.td}>{type.name}</td>
                  <td style={styles.td}>{type.category_name}</td>
                  <td style={styles.td}>
                    {type.measure_name} ({type.measure_symbol})
                  </td>
                  <td style={styles.td}>{type.measure_kind}</td>
                  {canManage && (
                    <td style={styles.td}>
                      <button
                        type="button"
                        style={styles.button}
                        onClick={() => {
                          setEditingTypeId(type.id);
                          setTypeForm({
                            name: type.name,
                            category: String(type.category),
                            measure: String(type.measure),
                          });
                        }}
                      >
                        Edit
                      </button>{" "}
                      <button type="button" style={styles.danger} onClick={() => remove("/work-types/", type, "work type")}>
                        Delete
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {canManage && <MaterialNorms />}
    </div>
  );
}

export default WorkTypesPage;
