"use client";

import * as React from "react";
import { X } from "lucide-react";

import { useCoreAuth } from "@/components/v5/core/auth";
import { UserAvatar } from "@/components/v5/core/user-menu";
import { core, type User } from "@/lib/v5/core";
import { cn } from "@/lib/utils";

let cache: User[] | null = null;

/** The user directory, fetched once per page view. */
export function useDirectory(): User[] {
  const [users, setUsers] = React.useState<User[]>(cache ?? []);
  React.useEffect(() => {
    if (cache) return;
    let live = true;
    core.users().then((r) => { cache = r.users; if (live) setUsers(r.users); }, () => undefined);
    return () => { live = false; };
  }, []);
  return users;
}

/** Recipients picked from the directory: chips plus a typeahead. `exclude` hides people (the sender). */
export function UserPicker({ label, value, onChange, exclude = [], testId }: {
  label: string; value: string[]; onChange: (v: string[]) => void; exclude?: string[]; testId: string;
}) {
  const users = useDirectory();
  const { effective } = useCoreAuth();
  const [text, setText] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);
  const byName = React.useMemo(() => new Map(users.map((u) => [u.username, u])), [users]);
  const options = users.filter((u) => u.username !== effective?.username && !exclude.includes(u.username)
    && !value.includes(u.username)
    && (!text.trim() || `${u.name} ${u.username} ${u.role}`.toLowerCase().includes(text.trim().toLowerCase())));

  React.useEffect(() => {
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  function add(u: User) {
    onChange([...value, u.username]);
    setText("");
    setOpen(false);
  }

  return (
    <div className="flex items-start gap-2" ref={ref} data-testid={testId}>
      <span className="w-8 shrink-0 pt-2 text-xs font-medium text-text-muted">{label}</span>
      <div className="relative min-w-0 flex-1">
        <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 focus-within:border-accent">
          {value.map((u) => (
            <span key={u} className="inline-flex items-center gap-1 rounded-full bg-accent-muted py-0.5 pl-1 pr-1.5 text-xs text-accent" data-testid={`${testId}-chip`} data-username={u}>
              {byName.get(u) ? <UserAvatar user={byName.get(u)!} size={18} /> : null}
              {byName.get(u)?.name ?? u}
              <button type="button" onClick={() => onChange(value.filter((x) => x !== u))} aria-label={`Remove ${byName.get(u)?.name ?? u}`}><X className="size-3" /></button>
            </span>
          ))}
          <input value={text} onChange={(e) => { setText(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)}
                 onKeyDown={(e) => {
                   if (e.key === "Enter" && options[0]) { e.preventDefault(); add(options[0]); }
                   if (e.key === "Escape") setOpen(false);
                   if (e.key === "Backspace" && !text && value.length) onChange(value.slice(0, -1));
                 }}
                 placeholder={value.length ? "" : "Add people"} aria-label={`${label} recipients`} data-testid={`${testId}-input`}
                 className="min-w-[120px] flex-1 bg-transparent py-1 text-sm text-text-primary outline-none placeholder:text-text-muted" />
        </div>
        {open && options.length > 0 ? (
          <ul className="absolute z-30 mt-1 max-h-60 w-full overflow-y-auto rounded-md border border-border bg-surface p-1 shadow-lg" role="listbox" data-testid={`${testId}-options`}>
            {options.map((u) => (
              <li key={u.username}>
                <button type="button" role="option" aria-selected="false" onClick={() => add(u)} data-username={u.username}
                        className={cn("flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-surface-hover")}>
                  <UserAvatar user={u} size={22} />
                  <span className="min-w-0"><span className="block truncate text-text-primary">{u.name}</span><span className="block truncate text-xs text-text-muted">{u.role}</span></span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
