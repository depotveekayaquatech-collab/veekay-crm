import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

const KEY = "veekay-theme";
const listeners = new Set<() => void>();

function read(): Theme {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return document.documentElement.classList.contains("dark") ? "dark" : "light"; // storage blocked: keep what's applied
  }
}

/** Freeze every transition for the frame the theme flips, so borders, placeholders, text and fills all change together. */
function withoutTransitions(change: () => void) {
  const root = document.documentElement;
  root.classList.add("theme-switching");
  change();
  void root.offsetHeight; // commit the new colours with transitions off
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove("theme-switching")));
}

function apply(theme: Theme) {
  withoutTransitions(() => applyNow(theme));
}

function applyNow(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#0d1424" : "#2f6fed");
}

/** Persist the choice, apply it right away, and tell every `useTheme` subscriber. */
export function setTheme(theme: Theme) {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* private mode: the theme still applies for this visit */
  }
  apply(theme);
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme(): [Theme, (theme: Theme) => void] {
  const theme = useSyncExternalStore(subscribe, read, () => "light" as Theme);
  return [theme, setTheme];
}
