export function pct(value: unknown): string {
  return value === null || value === undefined || value === "" ? "-" : `${(Number(value) * 100).toFixed(2)}%`;
}

export function num(value: unknown, digits = 2): string {
  return value === null || value === undefined || value === "" ? "-" : Number(value).toFixed(digits);
}

export function money(value: unknown): string {
  return value === null || value === undefined || value === "" ? "-" : `¥${Number(value).toFixed(2)}`;
}

export function dateText(value: unknown): string {
  return value ? String(value).slice(0, 10) : "暂无";
}

export function scoreText(value: unknown): string {
  return value === null || value === undefined || value === "" ? "-" : Number(value).toFixed(2);
}
