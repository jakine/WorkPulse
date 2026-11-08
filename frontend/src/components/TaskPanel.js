import { useCallback, useEffect, useState } from "react";
import { api, apiList } from "../api/client";
import { useAuth, useRole } from "../context/AuthContext";
import ActivityList from "./ActivityList";
import AttachmentGrid from "./AttachmentGrid";
import { ErrorText, Field, PRIORITIES, PriorityBadge, WorkTypeOptions, formatWhen, styles } from "./ui";

const wide = { ...styles.input, width: "100%", boxSizing: "border-box" };

function toForm(task) {
  return {
    title: task.title,
    description: task.description,
    priority: task.priority,
    phase: task.phase ? String(task.phase) : "",
    team: task.team ?? "",
    work_type: task.work_type ?? "",
    assignee_user: task.assignee_user ?? "",
    start_date: task.start_date || "",
    due_date: task.due_date || "",
    planned_quantity: task.planned_quantity || "",
  };
}

function TaskPanel({ taskId, statuses, onClose, onChange }) {
  const { user } = useAuth();
  const { canManage, isLead } = useRole();
  const [task, setTask] = useState(null);
  const [form, setForm] = useState(null);
  const [teams, setTeams] = useState([]);
  const [workTypes, setWorkTypes] = useState([]);
  const [phases, setPhases] = useState([]);
  const [members, setMembers] = useState([]);
  const [comments, setComments] = useState([]);
  const [events, setEvents] = useState([]);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const detail = await api(`/tasks/${taskId}/`);
    const [teamRows, typeRows, phaseRows, memberRows, commentRows, eventRows] = await Promise.all([
      apiList(`/workplace-teams/?workplace=${detail.project}`),
      apiList("/work-types/"),
      apiList("/task-phases/"),
      apiList("/companies/members/"),
      api(`/tasks/${taskId}/comments/`),
      api(`/tasks/${taskId}/activity/`),
    ]);
    setTask(detail);
    setForm(toForm(detail));
    setTeams(teamRows);
    setWorkTypes(typeRows);
    setPhases(phaseRows);
    setMembers(memberRows);
    setComments(commentRows);
    setEvents(eventRows);
  }, [taskId]);

  useEffect(() => {
    setError("");
    load().catch((err) => setError(err.message));
  }, [load]);

  function setField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function run(action) {
    setError("");
    try {
      await action();
      await load();
      onChange();
    } catch (err) {
      setError(err.message);
    }
  }

  function save(event) {
    event.preventDefault();
    run(() =>
      api(`/tasks/${taskId}/`, {
        method: "PATCH",
        body: {
          title: form.title,
          description: form.description,
          priority: form.priority,
          phase: form.phase ? Number(form.phase) : undefined,
          team: form.team ? Number(form.team) : null,
          work_type: form.work_type ? Number(form.work_type) : null,
          assignee_user: form.assignee_user ? Number(form.assignee_user) : null,
          start_date: form.start_date || null,
          due_date: form.due_date || null,
          planned_quantity: form.planned_quantity || null,
        },
      })
    );
  }

  function changeStatus(statusId) {
    run(() => api(`/tasks/${taskId}/move/`, { method: "POST", body: { status: Number(statusId), position: 100000 } }));
  }

  function addComment(event) {
    event.preventDefault();
    run(async () => {
      await api(`/tasks/${taskId}/comments/`, { method: "POST", body: { body: comment } });
      setComment("");
    });
  }

  async function remove() {
    if (!window.confirm("Delete this task?")) return;
    setError("");
    try {
      await api(`/tasks/${taskId}/`, { method: "DELETE" });
      onChange();
      onClose();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <aside style={styles.panel} aria-label="Task details">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", gap: "1rem" }}>
        <div>
          <div style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
            {task ? `${task.key} · ${task.project_name}` : "Loading..."}
          </div>
          <h2 style={{ margin: "0.2rem 0 0" }}>{task?.title}</h2>
        </div>
        <button type="button" style={styles.quiet} onClick={onClose}>
          Close
        </button>
      </div>
      <ErrorText>{error}</ErrorText>
      {task && form && (
        <>
          <div style={styles.row}>
            <Field label="Status">
              <select style={styles.input} value={task.status} onChange={(e) => changeStatus(e.target.value)}>
                {statuses.map((status) => (
                  <option key={status.id} value={status.id}>
                    {status.name}
                  </option>
                ))}
              </select>
            </Field>
            <PriorityBadge value={task.priority} />
            {task.progress_percent != null && (
              <span>
                {task.done_quantity}/{task.planned_quantity}
                {task.measure_symbol ? ` ${task.measure_symbol}` : ""} · {task.progress_percent}%
              </span>
            )}
          </div>

          {canManage ? (
            <form onSubmit={save} style={{ display: "grid", gap: "0.75rem" }}>
              <Field label="Title">
                <input style={wide} value={form.title} onChange={(e) => setField("title", e.target.value)} required />
              </Field>
              <Field label="Description">
                <textarea
                  style={{ ...wide, minHeight: "5rem" }}
                  value={form.description}
                  onChange={(e) => setField("description", e.target.value)}
                />
              </Field>
              <div style={styles.row}>
                <Field label="Phase">
                  <select style={styles.input} value={form.phase} onChange={(e) => setField("phase", e.target.value)}>
                    {phases.map((phase) => (
                      <option key={phase.id} value={phase.id}>
                        {phase.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Priority">
                  <select style={styles.input} value={form.priority} onChange={(e) => setField("priority", e.target.value)}>
                    {PRIORITIES.map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <div style={styles.row}>
                <Field label="Team">
                  <select style={styles.input} value={form.team} onChange={(e) => setField("team", e.target.value)}>
                    <option value="">No team</option>
                    {teams.map((row) => (
                      <option key={row.id} value={row.team}>
                        {row.team_number} · {row.team_name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Work type">
                  <select style={styles.input} value={form.work_type} onChange={(e) => setField("work_type", e.target.value)}>
                    <option value="">Same as project</option>
                    <WorkTypeOptions types={workTypes} />
                  </select>
                </Field>
                <Field label="Assignee">
                  <select
                    style={styles.input}
                    value={form.assignee_user}
                    onChange={(e) => setField("assignee_user", e.target.value)}
                  >
                    <option value="">Nobody</option>
                    {members.map((member) => (
                      <option key={member.id} value={member.user}>
                        {member.email}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <div style={styles.row}>
                <Field label="Start">
                  <input style={styles.input} type="date" value={form.start_date} onChange={(e) => setField("start_date", e.target.value)} />
                </Field>
                <Field label="Due">
                  <input style={styles.input} type="date" value={form.due_date} onChange={(e) => setField("due_date", e.target.value)} />
                </Field>
                <Field
                  label={
                    workTypes.find((type) => String(type.id) === String(form.work_type))?.measure_symbol
                      ? `Planned (${workTypes.find((type) => String(type.id) === String(form.work_type)).measure_symbol})`
                      : task.measure_symbol
                        ? `Planned (${task.measure_symbol})`
                        : "Planned amount"
                  }
                >
                  <input
                    style={styles.input}
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={form.planned_quantity}
                    onChange={(e) => setField("planned_quantity", e.target.value)}
                  />
                </Field>
              </div>
              <div style={styles.row}>
                <button style={styles.button} type="submit">
                  Save
                </button>
                <button style={styles.danger} type="button" onClick={remove}>
                  Delete task
                </button>
              </div>
            </form>
          ) : (
            <div style={{ display: "grid", gap: "0.35rem" }}>
              {task.description && <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{task.description}</p>}
              <div>Phase: {task.phase_name}</div>
              <div>Team: {task.team_name ? `${task.team_number} · ${task.team_name}` : "—"}</div>
              <div>Work type: {task.work_type_name || "Same as project"}</div>
              <div>Assignee: {task.assignee_email || "—"}</div>
              <div>
                Dates: {task.start_date || "?"} → {task.due_date || "?"}
              </div>
            </div>
          )}

          <section>
            <h3 style={{ margin: "0 0 0.5rem" }}>Photos and files</h3>
            <AttachmentGrid
              targetType="work.task"
              targetId={task.id}
              canUpload={
                canManage ||
                (isLead && teams.some((row) => row.team === task.team && row.lead_user === user?.id))
              }
            />
          </section>

          <section>
            <h3 style={{ margin: "0 0 0.5rem" }}>Comments</h3>
            <ul style={{ listStyle: "none", padding: 0, margin: "0 0 0.75rem", display: "grid", gap: "0.6rem" }}>
              {comments.map((row) => (
                <li key={row.id} style={{ background: "var(--surface-2)", borderRadius: "8px", padding: "0.5rem 0.65rem" }}>
                  <div style={{ fontSize: "0.78rem", color: "var(--muted)" }}>
                    {row.author_email} · {formatWhen(row.created_at)}
                  </div>
                  <div style={{ whiteSpace: "pre-wrap" }}>{row.body}</div>
                </li>
              ))}
              {comments.length === 0 && <li style={{ color: "var(--faint)" }}>No comments yet.</li>}
            </ul>
            <form onSubmit={addComment} style={{ display: "grid", gap: "0.5rem" }}>
              <textarea
                style={{ ...wide, minHeight: "3.5rem" }}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Write a comment"
                required
              />
              <div>
                <button style={styles.button} type="submit">
                  Comment
                </button>
              </div>
            </form>
          </section>

          <section>
            <h3 style={{ margin: "0 0 0.5rem" }}>History</h3>
            <ActivityList events={events} />
          </section>
        </>
      )}
    </aside>
  );
}

export default TaskPanel;
