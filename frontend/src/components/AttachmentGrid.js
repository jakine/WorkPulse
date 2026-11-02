import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiList, apiUpload } from "../api/client";
import { useAuth, useRole } from "../context/AuthContext";
import { ErrorText, styles } from "./ui";

const ACCEPT = "image/jpeg,image/png,image/webp,application/pdf";

const grid = {
  listStyle: "none",
  padding: 0,
  margin: 0,
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(96px, 1fr))",
  gap: "0.6rem",
};
const tile = {
  position: "relative",
  aspectRatio: "1 / 1",
  border: "1px solid var(--line)",
  borderRadius: "var(--radius-sm)",
  background: "var(--surface-2)",
  overflow: "hidden",
};
const tileLink = {
  display: "grid",
  placeItems: "center",
  width: "100%",
  height: "100%",
  color: "var(--ink)",
  textDecoration: "none",
};
const removeButton = {
  position: "absolute",
  top: "0.3rem",
  right: "0.3rem",
  width: "1.5rem",
  height: "1.5rem",
  padding: 0,
  borderRadius: "999px",
  border: "1px solid var(--line)",
  background: "var(--surface)",
  color: "var(--danger)",
  cursor: "pointer",
  lineHeight: 1,
};

function sizeLabel(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function AttachmentGrid({ targetType, targetId, canUpload = false, locked = false }) {
  const { user } = useAuth();
  const { canManage } = useRole();
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const picker = useRef(null);

  const load = useCallback(
    () => apiList(`/attachments/?target_type=${targetType}&target_id=${targetId}`).then(setFiles),
    [targetType, targetId]
  );

  useEffect(() => {
    setError("");
    load().catch((err) => setError(err.message));
  }, [load]);

  async function upload(event) {
    const chosen = Array.from(event.target.files || []);
    event.target.value = "";
    if (chosen.length === 0) return;
    setBusy(true);
    setError("");
    try {
      for (const file of chosen) {
        const body = new FormData();
        body.append("target_type", targetType);
        body.append("target_id", String(targetId));
        body.append("file", file);
        await apiUpload("/attachments/", body);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      load().catch((err) => setError(err.message));
    }
  }

  async function remove(file) {
    if (!window.confirm(`Remove ${file.original_name}?`)) return;
    setError("");
    try {
      await api(`/attachments/${file.id}/`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div style={{ display: "grid", gap: "0.6rem" }}>
      <ErrorText>{error}</ErrorText>
      {files.length === 0 ? (
        <p style={{ margin: 0, color: "var(--faint)" }}>No photos or files yet.</p>
      ) : (
        <ul style={grid}>
          {files.map((file) => (
            <li key={file.id} style={tile}>
              <a
                href={file.url}
                target="_blank"
                rel="noreferrer"
                style={tileLink}
                title={`${file.original_name} · ${sizeLabel(file.size)} · ${file.uploaded_by_email || "unknown"}`}
              >
                {file.is_image ? (
                  <img
                    src={file.url}
                    alt={file.caption || file.original_name}
                    loading="lazy"
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  />
                ) : (
                  <span style={{ padding: "0.4rem", fontSize: "0.75rem", textAlign: "center", overflowWrap: "anywhere" }}>
                    <strong style={{ display: "block", color: "var(--accent)" }}>PDF</strong>
                    {file.original_name}
                  </span>
                )}
              </a>
              {!locked && (canManage || file.uploaded_by === user?.id) && (
                <button
                  type="button"
                  style={removeButton}
                  onClick={() => remove(file)}
                  aria-label={`Remove ${file.original_name}`}
                  title="Remove"
                >
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canUpload && !locked && (
        <div>
          <input ref={picker} type="file" accept={ACCEPT} multiple hidden onChange={upload} />
          <button type="button" style={styles.quiet} disabled={busy} onClick={() => picker.current?.click()}>
            {busy ? "Uploading…" : "Add photos or files"}
          </button>
        </div>
      )}
    </div>
  );
}

export default AttachmentGrid;
