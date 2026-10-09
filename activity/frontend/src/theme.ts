// Activity colour theme: "warm" (walnut + amber phosphor, default) or "cold"
// (blue-black + green phosphor). Both are the same role tokens in styles.css,
// switched on <html data-theme>. Persisted per device in localStorage, like the
// conjugation language toggle — it's a display preference, not account data.

export type Theme = "warm" | "cold";

const STORAGE_KEY = "hablemos.theme";

export function getTheme(): Theme {
  return localStorage.getItem(STORAGE_KEY) === "cold" ? "cold" : "warm";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(STORAGE_KEY, theme);
}

/** Pet tint that reads well on each theme's CRT (used for new pets' default swatch). */
export const THEME_ACCENT: Record<Theme, string> = {
  warm: "#f2b53f",
  cold: "#7cff6b",
};
