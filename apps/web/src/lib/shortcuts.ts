import type { Route } from "next";

/** `g` then one of these keys goes to the page. */
export const GO_KEYS: { key: string; href: Route; label: string }[] = [
  { key: "h", href: "/" as Route, label: "Home" },
  { key: "a", href: "/ask" as Route, label: "Ask" },
  { key: "e", href: "/explore" as Route, label: "Explore" },
  { key: "u", href: "/audit", label: "Audit" },
  { key: "m", href: "/memory", label: "Memory" },
  { key: "b", href: "/about", label: "About" },
];

export interface ShortcutGroup {
  title: string;
  /** Where the keys work, when not everywhere. */
  where?: string;
  items: { keys: string[]; action: string }[];
}

/** Every keyboard shortcut, in the order the help dialog and the About page list them. */
export const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "Everywhere",
    items: [
      { keys: ["?"], action: "Show or hide this list" },
      { keys: ["/"], action: "Focus the question box on Ask, otherwise the page search" },
      { keys: ["Ctrl K", "⌘ K"], action: "Focus the KEP search in the top bar" },
      { keys: ["t"], action: "Switch the theme (system, light, dark)" },
      { keys: ["Esc"], action: "Close a dialog, a search list or a menu" },
    ],
  },
  {
    title: "Go to a page",
    where: "Press g, then the letter",
    items: GO_KEYS.map((g) => ({ keys: [`g ${g.key}`], action: g.label })),
  },
  {
    title: "Ask",
    items: [
      { keys: ["Enter"], action: "Send the question" },
      { keys: ["Shift Enter"], action: "New line in the question" },
      { keys: ["Esc"], action: "Cancel the running question" },
    ],
  },
  {
    title: "Search lists",
    where: "KEP search and Explore search",
    items: [
      { keys: ["↓", "↑"], action: "Move through the results" },
      { keys: ["Home", "End"], action: "First or last result (Explore)" },
      { keys: ["Enter"], action: "Open the highlighted result, or KEP-n when the query is a number" },
    ],
  },
  {
    title: "KEP page",
    items: [
      { keys: ["o"], action: "Open the KEP on GitHub" },
      { keys: ["y"], action: "Open kep.yaml on GitHub" },
      { keys: ["a"], action: "Ask about this KEP" },
      { keys: ["←", "→"], action: "Previous or next tab, when a tab is focused" },
    ],
  },
  {
    title: "Findings table",
    where: "With a finding row focused (Tab into the table or click a row)",
    items: [
      { keys: ["j", "k"], action: "Next or previous finding" },
      { keys: ["Enter", "Space"], action: "Expand or collapse the finding" },
      { keys: ["o"], action: "Open the finding's KEP page" },
      { keys: ["d"], action: "Draft the fix as an issue text (nothing is posted)" },
      { keys: ["]", "["], action: "Next or previous page of findings" },
    ],
  },
];

/** True when the key event comes from a field that takes text, so single-letter shortcuts must not fire. */
export function isTyping(target: EventTarget | null): boolean {
  const t = target as HTMLElement | null;
  if (!t || !t.tagName) return false;
  const tag = t.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || t.isContentEditable;
}

/** Dispatched on `document` to open the shortcuts dialog from a button. */
export const SHORTCUTS_EVENT = "kep:shortcuts";
