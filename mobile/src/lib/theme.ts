export const C = {
  bg: "#0e1013",
  panel: "#15181d",
  panel2: "#1b1f26",
  line: "#262b33",
  text: "#e7e9ec",
  muted: "#8b939e",
  accent: "#5eead4",
  accentInk: "#062a25",
  warn: "#fbbf24",
  bad: "#f87171",
  good: "#4ade80",
};

export const statusColor = (s?: string) => (s === "critical" ? C.bad : s === "watch" ? C.warn : C.accent);
