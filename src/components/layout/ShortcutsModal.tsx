import { Modal } from "@/components/ui/Modal";

const isMac = typeof navigator !== "undefined" && /mac/i.test(navigator.platform);

function Keys({ keys }: { keys: string[] }) {
  return (
    <span className="flex items-center gap-1">
      {keys.map((k, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <span className="text-xs text-gray-400">{keys[0] === "G" ? "then" : "+"}</span>}
          <kbd className="min-w-[1.5rem] rounded-md border border-surface-border bg-surface-subtle px-1.5 py-0.5 text-center text-xs font-bold text-gray-700 shadow-sm">{k}</kbd>
        </span>
      ))}
    </span>
  );
}

export interface GoShortcut {
  key: string;
  label: string;
}

/** The "?" cheat-sheet. `go` lists the g-then-key jumps this user can actually use. */
export function ShortcutsModal({ open, onClose, go }: { open: boolean; onClose: () => void; go: GoShortcut[] }) {
  const mod = isMac ? "⌘" : "Ctrl";
  const groups: { title: string; rows: { keys: string[]; label: string }[] }[] = [
    {
      title: "Anywhere",
      rows: [
        { keys: [mod, "K"], label: "Open search and jump to a page or store" },
        { keys: ["?"], label: "Show this list" },
        ...go.map((g) => ({ keys: ["G", g.key.toUpperCase()], label: `Go to ${g.label}` })),
      ],
    },
    {
      title: "Orders",
      rows: [
        { keys: ["1–4"], label: "Switch between the Orders tabs" },
        { keys: ["/"], label: "Focus the search box" },
        { keys: ["Enter"], label: "Save a count and jump to the next store" },
        { keys: ["Esc"], label: "Clear the search box" },
      ],
    },
  ];

  return (
    <Modal open={open} onClose={onClose} title="Keyboard shortcuts" description="Work faster without leaving the keyboard." size="md">
      <div className="flex flex-col gap-5">
        {groups.map((g) => (
          <section key={g.title}>
            <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wider text-gray-400">{g.title}</h3>
            <ul className="divide-y divide-surface-border rounded-xl border border-surface-border">
              {g.rows.map((r) => (
                <li key={r.label} className="flex items-center justify-between gap-4 px-3.5 py-2.5 text-sm text-gray-700">
                  <span>{r.label}</span>
                  <Keys keys={r.keys} />
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </Modal>
  );
}
