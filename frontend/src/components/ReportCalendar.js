import { useState } from "react";

export function isoDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function parseDate(value) {
  if (!value) return new Date();
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? new Date() : date;
}

export function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

export function startOfWeek(date) {
  const next = new Date(date);
  const weekday = (next.getDay() + 6) % 7;
  next.setDate(next.getDate() - weekday);
  next.setHours(0, 0, 0, 0);
  return next;
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

export function todayIso() {
  return isoDate(new Date());
}

export function formatLongDay(value) {
  return parseDate(value).toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

export function weekDays(value) {
  const start = startOfWeek(parseDate(value));
  return Array.from({ length: 7 }, (_, index) => isoDate(addDays(start, index)));
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function ReportCalendar({ value, mode, markedDates = [], onChange, onModeChange }) {
  const selected = parseDate(value);
  const [cursor, setCursor] = useState(() => startOfMonth(selected));
  const today = todayIso();
  const marked = new Set(markedDates);

  const monthLabel = cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const first = startOfMonth(cursor);
  const gridStart = startOfWeek(first);
  const cells = Array.from({ length: 42 }, (_, index) => addDays(gridStart, index));
  const week = weekDays(value);

  return (
    <div className="cal">
      <div className="cal-toolbar">
        <div className="cal-month-nav">
          <button
            type="button"
            className="ghost-btn"
            onClick={() => {
              const next = new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1);
              setCursor(next);
              if (mode === "month") onChange(isoDate(next));
            }}
          >
            Previous
          </button>
          <strong>{monthLabel}</strong>
          <button
            type="button"
            className="ghost-btn"
            onClick={() => {
              const next = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1);
              setCursor(next);
              if (mode === "month") onChange(isoDate(next));
            }}
          >
            Next
          </button>
        </div>
        <div className="cal-modes">
          <button type="button" className={mode === "day" ? "ghost-btn is-on" : "ghost-btn"} onClick={() => onModeChange("day")}>
            Day
          </button>
          <button type="button" className={mode === "week" ? "ghost-btn is-on" : "ghost-btn"} onClick={() => onModeChange("week")}>
            Week
          </button>
          <button type="button" className={mode === "month" ? "ghost-btn is-on" : "ghost-btn"} onClick={() => onModeChange("month")}>
            Month
          </button>
          <button
            type="button"
            className="ghost-btn"
            onClick={() => {
              const now = todayIso();
              setCursor(startOfMonth(parseDate(now)));
              onChange(now);
            }}
          >
            Today
          </button>
        </div>
      </div>
      <div className="cal-weekdays">
        {WEEKDAYS.map((day) => (
          <span key={day}>{day}</span>
        ))}
      </div>
      <div className="cal-grid">
        {cells.map((date) => {
          const iso = isoDate(date);
          const outside = date.getMonth() !== cursor.getMonth();
          const isToday = iso === today;
          const isSelected =
            mode === "month"
              ? !outside
              : mode === "week"
                ? week.includes(iso)
                : iso === value;
          const isAnchor = iso === value;
          return (
            <button
              key={iso}
              type="button"
              aria-label={formatLongDay(iso)}
              aria-pressed={isAnchor}
              className={[
                "cal-day",
                outside ? "is-outside" : "",
                isToday ? "is-today" : "",
                isSelected ? "is-selected" : "",
                isAnchor ? "is-anchor" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={() => {
                setCursor(startOfMonth(date));
                onChange(iso);
              }}
            >
              <span>{date.getDate()}</span>
              {marked.has(iso) && <i className="cal-dot" />}
            </button>
          );
        })}
      </div>
      {mode === "week" && (
        <div className="cal-week-days">
          {week.map((iso) => (
            <button
              key={iso}
              type="button"
              className={iso === value ? "ghost-btn is-on" : "ghost-btn"}
              onClick={() => onChange(iso)}
            >
              {parseDate(iso).toLocaleDateString(undefined, { weekday: "short", day: "numeric" })}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default ReportCalendar;
