"use client";

import { useSyncExternalStore } from "react";

const root = () => document.documentElement;
function subscribe(cb: () => void) {
  const mo = new MutationObserver(cb);
  mo.observe(root(), { attributes: true, attributeFilter: ["data-theme"] });
  return () => mo.disconnect();
}
const snapshot = () => (root().dataset.theme === "light" ? "light" : "dark");

export default function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, snapshot, () => "dark");
  function toggle() {
    const next = theme === "light" ? "dark" : "light";
    root().dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {
      // storage blocked: the choice just won't persist
    }
  }
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
      className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line px-2.5 text-xs font-medium text-mut hover:text-ink focus:outline-none focus-visible:ring-2 focus-visible:ring-pri"
    >
      <span aria-hidden="true">{theme === "light" ? "☾" : "☀"}</span>
      {theme === "light" ? "Dark" : "Light"}
    </button>
  );
}
