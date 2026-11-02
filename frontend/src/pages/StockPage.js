import { useEffect, useState } from "react";
import { api, apiList } from "../api/client";
import MaterialRequestsQueue from "../components/MaterialRequestsQueue";
import StockLevels from "../components/StockLevels";
import { ErrorText, Field, styles } from "../components/ui";
import { useRole } from "../context/AuthContext";

function today() {
  return new Date().toISOString().slice(0, 10);
}

function StockPage() {
  const { canManage } = useRole();
  const [types, setTypes] = useState([]);
  const [items, setItems] = useState([]);
  const [locations, setLocations] = useState([]);
  const [lots, setLots] = useState([]);
  const [movements, setMovements] = useState([]);
  const [workplaces, setWorkplaces] = useState([]);
  const [error, setError] = useState("");
  const [typeForm, setTypeForm] = useState({ name: "", requires_expiration: false });
  const [itemForm, setItemForm] = useState({ name: "", unit: "", stock_type: "" });
  const [depotName, setDepotName] = useState("");
  const [receive, setReceive] = useState({ item: "", location: "", quantity: "", expires_on: "", received_on: today() });
  const [movement, setMovement] = useState({
    lot: "",
    kind: "consume",
    quantity: "",
    to_location: "",
    workplace: "",
    happened_on: today(),
    note: "",
  });

  async function load() {
    const [typeRows, itemRows, locationRows, lotRows, movementRows, workplaceRows] = await Promise.all([
      apiList("/stock-types/"),
      apiList("/stock-items/"),
      apiList("/locations/"),
      apiList("/stock-lots/"),
      apiList("/stock-movements/"),
      apiList("/projects/"),
    ]);
    setTypes(typeRows);
    setItems(itemRows);
    setLocations(locationRows);
    setLots(lotRows);
    setMovements(movementRows);
    setWorkplaces(workplaceRows);
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  const selectedItem = items.find((item) => String(item.id) === String(receive.item));

  async function submit(path, body, reset) {
    setError("");
    try {
      await api(path, { method: "POST", body });
      if (reset) reset();
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={styles.page}>
      <h1 style={{ margin: 0 }}>Stock</h1>
      <p style={{ margin: 0 }}>
        Stock is received into a depot. Using it on a project removes that quantity from the depot.
      </p>
      <ErrorText>{error}</ErrorText>
      {canManage && <MaterialRequestsQueue onChange={() => load().catch((err) => setError(err.message))} />}
      {canManage && <StockLevels items={items} locations={locations} version={lots} />}

      {!canManage && (
        <div style={styles.card}>
          <h2 style={{ marginTop: 0 }}>Stock on hand</h2>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Item</th>
                <th style={styles.th}>Location</th>
                <th style={styles.th}>Quantity</th>
                <th style={styles.th}>Expires</th>
              </tr>
            </thead>
            <tbody>
              {lots.map((lot) => (
                <tr key={lot.id}>
                  <td style={styles.td}>{lot.item_name}</td>
                  <td style={styles.td}>{lot.location_name}</td>
                  <td style={styles.td}>
                    {lot.quantity} {lot.unit}
                  </td>
                  <td style={styles.td}>{lot.expires_on || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {lots.length === 0 && <p>No stock yet.</p>}
        </div>
      )}

      {canManage && (
      <>
      <form
        style={styles.card}
        onSubmit={(event) => {
          event.preventDefault();
          submit("/stock-types/", typeForm, () => setTypeForm({ name: "", requires_expiration: false }));
        }}
      >
        <h2 style={{ marginTop: 0 }}>Stock type</h2>
        <div style={styles.row}>
          <Field label="Name">
            <input style={styles.input} value={typeForm.name} onChange={(e) => setTypeForm({ ...typeForm, name: e.target.value })} required />
          </Field>
          <label style={{ ...styles.field, justifyContent: "end" }}>
            <span>
              <input
                type="checkbox"
                checked={typeForm.requires_expiration}
                onChange={(e) => setTypeForm({ ...typeForm, requires_expiration: e.target.checked })}
              />{" "}
              Ask for an expiration date
            </span>
          </label>
          <button style={styles.button} type="submit">
            Add type
          </button>
        </div>
      </form>

      <form
        style={styles.card}
        onSubmit={(event) => {
          event.preventDefault();
          submit("/stock-items/", { ...itemForm, stock_type: Number(itemForm.stock_type) }, () =>
            setItemForm({ name: "", unit: "", stock_type: "" })
          );
        }}
      >
        <h2 style={{ marginTop: 0 }}>Item</h2>
        <div style={styles.row}>
          <Field label="Type">
            <select style={styles.input} value={itemForm.stock_type} onChange={(e) => setItemForm({ ...itemForm, stock_type: e.target.value })} required>
              <option value="">Choose</option>
              {types.map((type) => (
                <option key={type.id} value={type.id}>
                  {type.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Name">
            <input style={styles.input} value={itemForm.name} onChange={(e) => setItemForm({ ...itemForm, name: e.target.value })} required />
          </Field>
          <Field label="Unit">
            <input style={styles.input} value={itemForm.unit} onChange={(e) => setItemForm({ ...itemForm, unit: e.target.value })} required />
          </Field>
          <button style={styles.button} type="submit">
            Add item
          </button>
        </div>
      </form>

      <form
        style={styles.card}
        onSubmit={(event) => {
          event.preventDefault();
          submit("/locations/", { name: depotName }, () => setDepotName(""));
        }}
      >
        <h2 style={{ marginTop: 0 }}>Depots</h2>
        <div style={styles.row}>
          <Field label="Name">
            <input style={styles.input} value={depotName} onChange={(e) => setDepotName(e.target.value)} required />
          </Field>
          <button style={styles.button} type="submit">
            Add depot
          </button>
        </div>
        <p>
          {locations.filter((location) => location.kind === "depot").map((location) => location.name).join(", ") || "No depots yet."}
        </p>
      </form>

      <form
        style={styles.card}
        onSubmit={(event) => {
          event.preventDefault();
          submit(
            "/stock-lots/",
            {
              item: Number(receive.item),
              location: Number(receive.location),
              quantity: receive.quantity,
              received_on: receive.received_on,
              expires_on: receive.expires_on || null,
            },
            () => setReceive({ item: "", location: "", quantity: "", expires_on: "", received_on: today() })
          );
        }}
      >
        <h2 style={{ marginTop: 0 }}>Receive stock</h2>
        <div style={styles.row}>
          <Field label="Item">
            <select style={styles.input} value={receive.item} onChange={(e) => setReceive({ ...receive, item: e.target.value })} required>
              <option value="">Choose</option>
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.unit})
                </option>
              ))}
            </select>
          </Field>
          <Field label="Depot">
            <select style={styles.input} value={receive.location} onChange={(e) => setReceive({ ...receive, location: e.target.value })} required>
              <option value="">Choose</option>
              {locations
                .filter((location) => location.kind === "depot")
                .map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="Quantity">
            <input style={styles.input} type="number" min="0.01" step="0.01" value={receive.quantity} onChange={(e) => setReceive({ ...receive, quantity: e.target.value })} required />
          </Field>
          <Field label="Received">
            <input style={styles.input} type="date" value={receive.received_on} onChange={(e) => setReceive({ ...receive, received_on: e.target.value })} required />
          </Field>
          <Field label={selectedItem?.requires_expiration ? "Expiration" : "Expiration (optional)"}>
            <input
              style={styles.input}
              type="date"
              value={receive.expires_on}
              required={Boolean(selectedItem?.requires_expiration)}
              onChange={(e) => setReceive({ ...receive, expires_on: e.target.value })}
            />
          </Field>
          <button style={styles.button} type="submit">
            Receive
          </button>
        </div>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Item</th>
              <th style={styles.th}>Location</th>
              <th style={styles.th}>Quantity</th>
              <th style={styles.th}>Expires</th>
            </tr>
          </thead>
          <tbody>
            {lots.map((lot) => (
              <tr key={lot.id}>
                <td style={styles.td}>{lot.item_name}</td>
                <td style={styles.td}>{lot.location_name}</td>
                <td style={styles.td}>
                  {lot.quantity} {lot.unit}
                </td>
                <td style={styles.td}>{lot.expires_on || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </form>

      <form
        style={styles.card}
        onSubmit={(event) => {
          event.preventDefault();
          const body = {
            lot: Number(movement.lot),
            kind: movement.kind,
            quantity: movement.quantity,
            happened_on: movement.happened_on,
            note: movement.note,
          };
          if (movement.kind === "transfer") body.to_location = Number(movement.to_location);
          if (movement.workplace) body.workplace = Number(movement.workplace);
          submit("/stock-movements/", body, () =>
            setMovement({
              lot: "",
              kind: "consume",
              quantity: "",
              to_location: "",
              workplace: "",
              happened_on: today(),
              note: "",
            })
          );
        }}
      >
        <h2 style={{ marginTop: 0 }}>Use stock on a project</h2>
        <p style={{ marginTop: 0 }}>Using stock records a consume movement and takes that quantity off the depot lot.</p>
        <div style={styles.row}>
          <Field label="Lot">
            <select style={styles.input} value={movement.lot} onChange={(e) => setMovement({ ...movement, lot: e.target.value })} required>
              <option value="">Choose</option>
              {lots.map((lot) => (
                <option key={lot.id} value={lot.id}>
                  {lot.item_name} @ {lot.location_name} ({lot.quantity})
                </option>
              ))}
            </select>
          </Field>
          <Field label="Kind">
            <select style={styles.input} value={movement.kind} onChange={(e) => setMovement({ ...movement, kind: e.target.value })}>
              <option value="consume">Use on a project</option>
              <option value="transfer">Move to another depot</option>
              <option value="adjust">Adjust</option>
            </select>
          </Field>
          <Field label="Quantity">
            <input style={styles.input} type="number" step="0.01" value={movement.quantity} onChange={(e) => setMovement({ ...movement, quantity: e.target.value })} required />
          </Field>
          {movement.kind === "transfer" && (
            <Field label="To depot">
              <select style={styles.input} value={movement.to_location} onChange={(e) => setMovement({ ...movement, to_location: e.target.value })} required>
                <option value="">Choose</option>
                {locations
                  .filter((location) => location.kind === "depot")
                  .map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
              </select>
            </Field>
          )}
          <Field label="Project">
            <select
              style={styles.input}
              value={movement.workplace}
              required={movement.kind === "consume"}
              onChange={(e) => setMovement({ ...movement, workplace: e.target.value })}
            >
              <option value="">{movement.kind === "consume" ? "Choose" : "None"}</option>
              {workplaces.map((place) => (
                <option key={place.id} value={place.id}>
                  {place.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Date">
            <input style={styles.input} type="date" value={movement.happened_on} onChange={(e) => setMovement({ ...movement, happened_on: e.target.value })} required />
          </Field>
          <Field label="Note">
            <input style={styles.input} value={movement.note} onChange={(e) => setMovement({ ...movement, note: e.target.value })} />
          </Field>
          <button style={styles.button} type="submit">
            Record movement
          </button>
        </div>
        <ul>
          {movements.map((row) => (
            <li key={row.id}>
              {row.happened_on}: {row.kind} {row.quantity} {row.lot_item_name}
              {row.workplace_name ? ` → ${row.workplace_name}` : ""}
              {row.note ? ` (${row.note})` : ""}
            </li>
          ))}
        </ul>
      </form>
      </>
      )}
    </div>
  );
}

export default StockPage;
