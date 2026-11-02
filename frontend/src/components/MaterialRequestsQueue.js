import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiList } from "../api/client";
import { ErrorText, Field, formatDay, styles } from "./ui";

/** Office view: send what sites asked for from the depot, or reject a request. */
function MaterialRequestsQueue({ onChange }) {
  const [requests, setRequests] = useState([]);
  const [lots, setLots] = useState([]);
  const [sites, setSites] = useState(new Map());
  const [picks, setPicks] = useState({});
  const [notes, setNotes] = useState({});
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [requestRows, lotRows, locationRows] = await Promise.all([
      apiList("/material-requests/?status=open,partly_fulfilled"),
      apiList("/stock-lots/"),
      apiList("/locations/"),
    ]);
    setRequests(requestRows);
    setLots(lotRows.filter((lot) => Number(lot.quantity) > 0));
    setSites(new Map(locationRows.filter((row) => row.workplace).map((row) => [row.workplace, row.id])));
  }, []);

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, [load]);

  function setPick(lineId, key, value) {
    setPicks((current) => ({ ...current, [lineId]: { ...current[lineId], [key]: value } }));
  }

  async function run(action) {
    setError("");
    try {
      await action();
      await load();
      if (onChange) await onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  function send(request, line) {
    const pick = picks[line.id] || {};
    run(async () => {
      await api(`/material-requests/${request.id}/fulfil/`, {
        method: "POST",
        body: { picks: [{ line: line.id, lot: Number(pick.lot), quantity: pick.quantity }] },
      });
      setPicks((current) => ({ ...current, [line.id]: {} }));
    });
  }

  function reject(request) {
    run(() => api(`/material-requests/${request.id}/reject/`, { method: "POST", body: { note: notes[request.id] || "" } }));
  }

  return (
    <div style={styles.card}>
      <h2 style={{ marginTop: 0 }}>Requests from sites</h2>
      <ErrorText>{error}</ErrorText>
      {requests.length === 0 ? (
        <p style={{ margin: 0 }}>No open requests.</p>
      ) : (
        <div style={{ display: "grid", gap: "1rem" }}>
          {requests.map((request) => (
            <div key={request.id} style={{ display: "grid", gap: "0.6rem", paddingTop: "0.75rem", borderTop: "1px solid var(--line)" }}>
              <div>
                <strong>
                  #{request.id} · <Link to={`/projects/${request.workplace}?tab=stock`}>{request.workplace_name}</Link>
                </strong>
                <span style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                  {" "}
                  · {request.requested_by_email}
                  {request.needed_by ? ` · needed by ${formatDay(request.needed_by)}` : ""} · {request.status_label}
                </span>
                {request.note && <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>{request.note}</div>}
              </div>
              {request.lines.map((line) => {
                const left = Math.max(Number(line.quantity) - Number(line.fulfilled_quantity), 0);
                const choices = lots.filter((lot) => lot.item === line.item && lot.location !== sites.get(request.workplace));
                const pick = picks[line.id] || {};
                return (
                  <div key={line.id} style={{ ...styles.row, alignItems: "end" }}>
                    <div style={{ minWidth: "12rem" }}>
                      <div style={{ fontWeight: 600 }}>{line.item_name}</div>
                      <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
                        {line.fulfilled_quantity} of {line.quantity} {line.unit} sent · {left.toFixed(2)} {line.unit} left
                      </div>
                    </div>
                    {left > 0 &&
                      (choices.length === 0 ? (
                        <span style={{ color: "var(--warn)" }}>No {line.item_name} in stock elsewhere.</span>
                      ) : (
                        <>
                          <Field label="From">
                            <select style={styles.input} value={pick.lot || ""} onChange={(e) => setPick(line.id, "lot", e.target.value)}>
                              <option value="">Choose stock</option>
                              {choices.map((lot) => (
                                <option key={lot.id} value={lot.id}>
                                  {lot.location_name} · {lot.quantity} {lot.unit}
                                  {lot.expires_on ? ` · expires ${lot.expires_on}` : ""}
                                </option>
                              ))}
                            </select>
                          </Field>
                          <Field label={`Send (${line.unit})`}>
                            <input
                              style={styles.input}
                              type="number"
                              min="0.01"
                              step="0.01"
                              value={pick.quantity ?? ""}
                              placeholder={left.toFixed(2)}
                              onChange={(e) => setPick(line.id, "quantity", e.target.value)}
                            />
                          </Field>
                          <button
                            type="button"
                            style={styles.button}
                            disabled={!pick.lot || !pick.quantity}
                            onClick={() => send(request, line)}
                          >
                            Send to site
                          </button>
                        </>
                      ))}
                  </div>
                );
              })}
              <div style={styles.row}>
                <Field label="Reason to reject">
                  <input
                    style={styles.input}
                    value={notes[request.id] || ""}
                    onChange={(e) => setNotes({ ...notes, [request.id]: e.target.value })}
                  />
                </Field>
                <button type="button" style={styles.danger} disabled={!notes[request.id]} onClick={() => reject(request)}>
                  Reject request
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default MaterialRequestsQueue;
