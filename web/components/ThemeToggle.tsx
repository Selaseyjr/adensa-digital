"use client";

/**
 * Theme toggle: Light workspace ↔ Dark Command Centre (v1).
 *
 * The only stateful piece of the theming system. It flips
 * [data-theme] on <html>; the init script in layout.tsx has
 * already applied the persisted choice before hydration, so
 * first paint never flashes. Selection persists in
 * localStorage ("adensa-theme") and defaults to the light
 * workspace (no prefers-color-scheme override — the command
 * centre is a deliberate operational choice, not a system
 * inference).
 *
 * Voice: the control is named as an environment choice —
 * "Command Centre", never "dark mode fun" — and the button's
 * accessible label always states the action, not the state.
 */

import { useEffect, useState } from "react";

const STORAGE_KEY = "adensa-theme";

function writeStoredTheme(theme: string) {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Private-mode / storage-disabled: session-only choice.
  }
}

export function ThemeToggle() {
  // Initialize from the DOM attribute the init script set, so
  // server and client renders agree (no hydration mismatch).
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    if (typeof document !== "undefined") {
      return document.documentElement.dataset.theme === "dark"
        ? "dark"
        : "light";
    }
    return "light";
  });

  useEffect(() => {
    // Defensive re-sync: React 19 hydration recovers <html> to its
    // VDOM attributes, which can drop the pre-hydration data-theme
    // set by the layout init script (hydration-time only). Theme
    // data is not a React prop, so re-asserting the user's choice
    // here is idempotent and keeps the DOM authoritative.
    document.documentElement.dataset.theme = theme;

    // Re-sync in case another tab changed the choice.
    const onStorage = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY) {
        const next = event.newValue === "dark" ? "dark" : "light";
        setTheme(next);
        document.documentElement.dataset.theme = next;
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [theme]);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    writeStoredTheme(next);
  }

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-pressed={theme === "dark"}
      title={
        theme === "dark"
          ? "Switch to the light workspace"
          : "Switch to the dark Command Centre"
      }
    >
      <span className="theme-toggle-label">
        {theme === "dark" ? "Daylight" : "Command Centre"}
      </span>
    </button>
  );
}
