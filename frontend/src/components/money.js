import { labelFor, styles } from "./ui";

/** A right-aligned table cell for amounts. */
export const num = { ...styles.td, textAlign: "right", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" };

export function formatMoney(value, currency = "EUR") {
  const number = Number(value || 0);
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(number);
  } catch {
    return `${number.toFixed(2)} ${currency}`;
  }
}

export const PAY_TYPES = [
  ["daily", "Per day"],
  ["weekly", "Per week"],
  ["monthly", "Per month"],
  ["not_paid_here", "Not paid through WorkPulse"],
];

export function payTypeLabel(value) {
  return labelFor(PAY_TYPES, value) || "No rate";
}

export const METHODS = [
  ["cash", "Cash"],
  ["bank", "Bank transfer"],
  ["other", "Other"],
];
