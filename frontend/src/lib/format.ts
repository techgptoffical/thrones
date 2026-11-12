export function bytes(n: number): string {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  const v = n / 1024 ** i;
  return `${v >= 100 || i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`;
}

export function mb(n: number | null | undefined): string {
  if (n == null) return "—";
  return n >= 1024 ? `${(n / 1024).toFixed(1)} GB` : `${n} MB`;
}

export function seconds(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 10) return `${n.toFixed(1)} s`;
  if (n < 60) return `${Math.round(n)} s`;
  return `${Math.floor(n / 60)}m ${Math.round(n % 60)}s`;
}

export function dayBucket(ts: number): string {
  const d = new Date(ts * 1000);
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const diff = (start.getTime() - new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()) / 86400000;
  if (diff <= 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff <= 7) return "Previous 7 days";
  if (diff <= 30) return "Previous 30 days";
  return "Older";
}

export function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Still up?";
  if (h < 12) return "Good morning.";
  if (h < 17) return "Good afternoon.";
  return "Good evening.";
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}
