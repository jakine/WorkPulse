export const styles = {
  page: { display: "grid", gap: "1.25rem" },
  card: {
    background: "var(--surface)",
    border: "1px solid var(--line)",
    borderRadius: "var(--radius)",
    padding: "1.1rem 1.25rem",
    boxShadow: "var(--shadow)",
  },
  row: { display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "end" },
  field: { display: "flex", flexDirection: "column", gap: "0.35rem", minWidth: "10rem" },
  label: { fontSize: "0.78rem", fontWeight: 600, color: "var(--muted)" },
  input: {
    padding: "0.55rem 0.7rem",
    border: "1px solid var(--line)",
    borderRadius: "var(--radius-sm)",
    fontSize: "0.95rem",
    background: "var(--surface)",
    color: "var(--ink)",
  },
  button: {
    padding: "0.55rem 0.95rem",
    backgroundColor: "var(--accent)",
    color: "var(--accent-ink)",
    border: "none",
    borderRadius: "var(--radius-sm)",
    fontWeight: 650,
    cursor: "pointer",
  },
  quiet: {
    padding: "0.45rem 0.75rem",
    background: "var(--surface)",
    color: "var(--ink)",
    border: "1px solid var(--line)",
    borderRadius: "var(--radius-sm)",
    cursor: "pointer",
  },
  danger: {
    padding: "0.35rem 0.65rem",
    background: "var(--danger-soft)",
    color: "var(--danger)",
    border: "1px solid transparent",
    borderRadius: "var(--radius-sm)",
    cursor: "pointer",
  },
  error: { color: "var(--danger)", margin: 0 },
  table: { width: "100%", borderCollapse: "collapse", fontSize: "0.92rem" },
  th: {
    textAlign: "left",
    padding: "0.55rem 0.45rem",
    borderBottom: "1px solid var(--line)",
    color: "var(--muted)",
    fontSize: "0.75rem",
    letterSpacing: "0.04em",
    textTransform: "uppercase",
  },
  td: { padding: "0.55rem 0.45rem", borderBottom: "1px solid var(--line)", verticalAlign: "top" },
  stats: { display: "flex", gap: "1rem", flexWrap: "wrap" },
  stat: {
    background: "var(--surface)",
    border: "1px solid var(--line)",
    borderRadius: "var(--radius)",
    padding: "0.95rem 1.1rem",
    minWidth: "9rem",
    boxShadow: "var(--shadow)",
  },
};

export function Field({ label, children }) {
  return (
    <label style={styles.field}>
      <span style={styles.label}>{label}</span>
      {children}
    </label>
  );
}

export function ErrorText({ children }) {
  if (!children) return null;
  return <p style={styles.error}>{children}</p>;
}

export function PageHeader({ title, children }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {children ? <p className="lede">{children}</p> : null}
      </div>
    </header>
  );
}

export function defaultPhaseId(phases) {
  const execution = phases.find((phase) => phase.name === "Execution");
  return String((execution || phases[0] || {}).id || "");
}

export const PRIORITIES = [
  ["low", "Low"],
  ["medium", "Medium"],
  ["high", "High"],
  ["urgent", "Urgent"],
];

export function WorkTypeOptions({ types }) {
  const groups = [];
  const index = new Map();
  types.forEach((type) => {
    const name = type.category_name || "General";
    if (!index.has(name)) {
      index.set(name, groups.length);
      groups.push({ name, types: [] });
    }
    groups[index.get(name)].types.push(type);
  });
  return groups.map((group) => (
    <optgroup key={group.name} label={group.name}>
      {group.types.map((type) => (
        <option key={type.id} value={type.id}>
          {type.name} ({type.measure_symbol})
        </option>
      ))}
    </optgroup>
  ));
}

export function labelFor(options, value) {
  const match = options.find(([key]) => key === value);
  return match ? match[1] : value;
}

const PRIORITY_COLORS = { low: "#8a8276", medium: "#1e5c52", high: "#b9770e", urgent: "#b42318" };

export function Badge({ children, color = "var(--accent)" }) {
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: "0.72rem",
        fontWeight: 650,
        color,
        background: "var(--surface-2)",
        border: `1px solid color-mix(in srgb, ${color} 45%, var(--line))`,
        borderRadius: "999px",
        padding: "0.08rem 0.5rem",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

export function PriorityBadge({ value }) {
  return <Badge color={PRIORITY_COLORS[value] || "var(--muted)"}>{labelFor(PRIORITIES, value)}</Badge>;
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div
      style={{
        display: "flex",
        gap: "0.2rem",
        borderBottom: "1px solid var(--line)",
        flexWrap: "wrap",
      }}
    >
      {tabs.map(([key, label]) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          style={{
            padding: "0.6rem 0.95rem",
            border: "none",
            borderBottom: value === key ? "2px solid var(--accent)" : "2px solid transparent",
            background: "transparent",
            color: value === key ? "var(--ink)" : "var(--muted)",
            fontWeight: value === key ? 650 : 500,
            cursor: "pointer",
          }}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function formatWhen(value) {
  if (!value) return "";
  return new Date(value).toLocaleString();
}

export function companyToday(company) {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: company?.timezone || undefined,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${value.year}-${value.month}-${value.day}`;
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}

export function formatDay(value) {
  if (!value) return "";
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
