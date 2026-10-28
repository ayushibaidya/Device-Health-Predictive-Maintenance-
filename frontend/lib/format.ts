export function number(value: number | null | undefined, digits = 2): string {
  return value == null ? "Unavailable" : new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
  }).format(value);
}

export function timestamp(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    second: "2-digit", hourCycle: "h23", timeZone: "UTC",
  }).format(new Date(value)) + " UTC";
}

export function stateLabel(value: string): string {
  return value.charAt(0) + value.slice(1).toLowerCase();
}
