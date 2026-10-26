/**
 * PLAN_R12 Session G (R11_FEEDBACK I6): where a Deal Desk (i) panel goes. Pure, so it is tested (dealdesk-popover.test.ts).
 *
 * The panel opens below its (i) when it fits, else above when there is more room there; it never leaves the viewport:
 * it shifts sideways to stay inside the margins, its width is capped to the viewport, and its height to the room on the
 * chosen side (the panel scrolls inside). The panel is rendered fixed, in a portal on <body>, above every table and chart.
 */

export interface AnchorRect { top: number; left: number; right: number; bottom: number }
export interface Size { width: number; height: number }
export interface Placement { top: number; left: number; width: number; maxHeight: number; side: "below" | "above" }

export const PANEL_MAX_WIDTH = 416; // 26rem
export const MARGIN = 8;
export const GAP = 6;

export function placePanel(anchor: AnchorRect, panel: Size, view: Size, align: "left" | "right" = "left"): Placement {
  const width = Math.max(160, Math.min(panel.width || PANEL_MAX_WIDTH, PANEL_MAX_WIDTH, view.width - 2 * MARGIN));
  const below = view.height - anchor.bottom - GAP - MARGIN;
  const above = anchor.top - GAP - MARGIN;
  const side: Placement["side"] = panel.height <= below || below >= above ? "below" : "above";
  const room = Math.max(120, side === "below" ? below : above);
  const h = Math.min(panel.height || room, room);
  const top = side === "below" ? anchor.bottom + GAP : Math.max(MARGIN, anchor.top - GAP - h);
  const want = align === "right" ? anchor.right - width : anchor.left;
  const left = Math.min(Math.max(MARGIN, want), Math.max(MARGIN, view.width - MARGIN - width));
  return { top: Math.round(top), left: Math.round(left), width: Math.round(width), maxHeight: Math.round(room), side };
}

/** True when the panel sits fully inside the viewport (the UAT check on every (i)). */
export function inBounds(p: { top: number; left: number; width: number; height: number }, view: Size): boolean {
  return p.left >= 0 && p.top >= 0 && p.left + p.width <= view.width + 0.5 && p.top + p.height <= view.height + 0.5;
}
