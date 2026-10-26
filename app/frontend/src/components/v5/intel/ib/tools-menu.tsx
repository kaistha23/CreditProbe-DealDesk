"use client";

/**
 * R13 IB: a small "Tools" (or "More") menu button — the mantra's way to reach R13 engines without first-screen clutter.
 * Items are {key, label}; picking one calls `onPick(key)`. Closes on Escape and outside click.
 */

import { Wrench } from "lucide-react";

import { Dropdown } from "@/components/v5/ui/dropdown"; // R14 U (K28)

export function ToolsMenu({ items, onPick, label = "Tools", testId = "tools-menu", className }: {
  items: { key: string; label: string; hint?: string }[]; onPick: (key: string) => void; label?: string; testId?: string; className?: string;
}) {
  // R14 U (K28): the house dropdown (hint shown as the muted description).
  return (
    <Dropdown label={label} icon={<Wrench />} className={className} buttonTestId={testId} menuTestId={`${testId}-menu`}
              sections={[{ items: items.map((it) => ({ key: it.key, label: it.label, description: it.hint, testId: `${testId}-${it.key}`,
                                                      onSelect: () => onPick(it.key) })) }]} />
  );
}
