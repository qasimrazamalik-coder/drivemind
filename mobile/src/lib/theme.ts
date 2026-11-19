/**
 * DriveMind colours: "the filing cabinet". Painted-steel greys, manila folder yellow for what is
 * stored, cabinet green for actions. Same palette as the PC dashboard, in light and dark.
 *
 * `C` is one shared object that always holds the active palette. Screens read it while they
 * render, so switching the theme swaps its contents and remounts the app (see appearance.tsx).
 */
export type Scheme = "light" | "dark";
export type ThemePref = "system" | Scheme;

const DARK = {
  bg: "#141817",
  panel: "#1d2220",
  panel2: "#242a27",
  line: "#333a36",
  text: "#e5e8e1",
  muted: "#a3aaa3",
  accent: "#62b79c",
  accentInk: "#0d1f19",
  accentSoft: "rgba(98,183,156,0.16)",
  manila: "#e7ba4c",
  manilaInk: "#2b2004",
  warn: "#e8a945",
  warnSoft: "rgba(232,169,69,0.16)",
  bad: "#f08a7e",
  good: "#8fcf8a",
};

const LIGHT: typeof DARK = {
  bg: "#e6e8e1",
  panel: "#f7f8f3",
  panel2: "#eceee7",
  line: "#d3d7cd",
  text: "#1c2220",
  muted: "#555d58",
  accent: "#1e5b4b",
  accentInk: "#ffffff",
  accentSoft: "rgba(30,91,75,0.11)",
  manila: "#e2b23f",
  manilaInk: "#3a2c06",
  warn: "#8a5300",
  warnSoft: "rgba(138,83,0,0.10)",
  bad: "#a8251c",
  good: "#2f6b3a",
};

export const C: typeof DARK = { ...DARK };

/** Archivo for headings and the numbers that matter; body text stays in the phone's own font. */
export const F = { display: "Archivo_800ExtraBold", strong: "Archivo_700Bold" };

let current: Scheme = "dark";
const listeners: (() => void)[] = [];

/** Run `fn` whenever the palette changes (the shared style sheet uses this to rebuild). */
export function onPaletteChange(fn: () => void) {
  listeners.push(fn);
}

export function applyScheme(scheme: Scheme) {
  if (scheme === current) return;
  current = scheme;
  Object.assign(C, scheme === "light" ? LIGHT : DARK);
  listeners.forEach((fn) => fn());
}

export const currentScheme = () => current;

export const statusColor = (s?: string) => (s === "critical" ? C.bad : s === "watch" ? C.warn : C.accent);
