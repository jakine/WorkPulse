export const WEEKDAYS = [
  ["mon", "Mon"],
  ["tue", "Tue"],
  ["wed", "Wed"],
  ["thu", "Thu"],
  ["fri", "Fri"],
  ["sat", "Sat"],
  ["sun", "Sun"],
];

export function hoursLabel(value) {
  const number = Number(value);
  return number ? String(number) : "–";
}

export function versionOn(versions, day) {
  let current = null;
  for (const version of versions) {
    if (version.valid_from && version.valid_from > day) break;
    current = version;
  }
  return current;
}
