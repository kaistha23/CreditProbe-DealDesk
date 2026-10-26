import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  BookOpenCheck,
  Bot,
  Boxes,
  Brain,
  ClipboardCheck,
  ScrollText,
  Database,
  FileText,
  Inbox,
  MessagesSquare,
  FlaskConical,
  Handshake,
  Gauge,
  GitBranch,
  LayoutGrid,
  Network,
  Radar,
  Search,
  Settings,
  Sparkles,
  Users,
  FileSpreadsheet,
} from "lucide-react";

/**
 * The CreditProbe AI capability map.
 *
 * One definition of what the product contains — the sidebar, the landing page
 * and every page header read it, so a capability can never appear in one place
 * and not another.
 *
 * The WORK group follows the product hierarchy exactly:
 *
 *     Project        the master workspace
 *       Investigation  a conversational thread
 *         Analysis       one deterministic engine result
 *
 * so Work lists Projects, Investigations and Analyses in that order, then Playbook (the
 * reports built from them) and Policy Docs (PLAN_R3: it replaced Documents).
 * Analysis Studio stays under DATA (was BUILD) because it defines analytical *capabilities*
 * rather than holding executed results. It replaced Engine Builder in the
 * navigation: the registered engine analyses are still there, still certified
 * and still reachable, but they are now one kind of implementation behind a
 * method rather than the whole of what the product can compute. The
 * /engine-builder routes remain for the analyses that link to them.
 *
 * `status` is part of the model rather than a comment. The product rule is that
 * the UI must never present a placeholder as production functionality, and the
 * only reliable way to honour that is to make every screen carry its own honest
 * status and render it.
 */
export type CapabilityStatus =
  /** Working on real engine or Data Builder results, end to end. */
  | "live"
  /** Real, on a deliberately narrow path, or partly demo-seeded. */
  | "partial"
  /** Designed and structurally real, not yet interactive. */
  | "preview"
  /** Not started; the route exists so navigation is complete. */
  | "planned";

export type NavGroup = "Home" | "Functionalities" | "Work" | "Intelligence" | "Data" | "Govern" | "Admin";

/**
 * The client-demo scope freeze.
 *
 * Distinct from `status`, and the distinction is the point. `status` says how
 * finished a capability is; `demo` says whether it is part of tomorrow's
 * demonstration. A capability can be perfectly finished and still not belong
 * in a twenty-minute walkthrough, and one that is honestly labelled
 * "Placeholder by design" is finished enough to ship and wrong to show.
 *
 *   core     Shown, and must be reliable.
 *   optional Shown only if every check passes; the presenter may skip it.
 *   admin    Reachable by an authorized user, not part of the walkthrough.
 *   hidden   Removed from navigation while Demo Mode is on.
 *
 * `hidden` removes the LINK, not the route. Anyone who types the address
 * still gets the page, because hiding a screen is presentation, never
 * security — the API behind it enforces permission whatever the sidebar
 * shows.
 */
export type DemoScope = "core" | "optional" | "admin" | "hidden";

export const DEMO_SCOPE_LABEL: Record<DemoScope, string> = {
  core: "Core"    ,
  optional: "Optional",
  admin: "Admin preview",
  hidden: "Hidden in presentation mode",
};

export interface NavItem {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
  status: CapabilityStatus;
  phase: string;
  group: NavGroup;
  /**
   * Which roles see this in the sidebar. Absent means everybody.
   *
   * Hiding a link is COURTESY, not security — §28's Agent Operations is
   * enforced by `principals.require_operate` on every endpoint behind it, and
   * a Viewer who types the URL gets a 403 rather than a screen. What this
   * prevents is a sidebar full of things the reader cannot open.
   */
  roles?: string[];
  /**
   * Where this sits in the client-demo scope freeze. See
   * `docs/DEMO_SCOPE_FREEZE.md` for why each one is classified as it is.
   */
  demo: DemoScope;
  /** Why, in one line, when the answer is not obvious. */
  demoNote?: string;
}

// PLAN_R10 S1: the R6/R7 grouping again. Home (the Cockpit, landing page after sign-in), Intelligence, Work, Data,
// Admin at the bottom. "Functionalities" is kept in the type for old imports; no item uses it.
export const NAV_GROUPS: NavGroup[] = [
  "Home",
  "Intelligence",
  "Work",
  "Data",
  "Govern",
  "Admin",
];

/**
 * PLAN_R10 S1: screens removed from the navigation, and where their routes now go. The pages themselves redirect
 * (app/intelligence, app/queries, app/accepted-risk); this map is the one place that says so, for links and tests.
 */
export const REMOVED_ROUTES: Readonly<Record<string, string>> = {
  "/intelligence": "/",
  "/queries": "/",
  "/accepted-risk": "/early-warning",
};

/**
 * The edition this build is (Deal Desk edition, October 2026).
 *
 * `dealdesk` (the default on the dealdesk-edition branch) is CreditProbe with Deal Desk as its one intelligence
 * module: the Cockpit stays the landing page after sign-in (its brief and its Ask are Deal Desk's, see
 * components/home), and Deal Desk and everything it draws on stay (the Work group, Data Domains and Analysis Studio,
 * Trace, the Admin group); BRF, Lenses, Early Warning, Playbooks, Stress Testing, What-If, Borrower 360 and the
 * Scorecard leave the navigation and their routes redirect to Deal Desk (next.config.ts carries the same list as
 * HTTP redirects, so a typed address lands on Deal Desk too). The screens' code stays in the tree because Deal Desk
 * and the Work panels import from it (the Plotly wrapper, the answer blocks, the thread trace); nothing is rendered
 * through it. `full` is the whole product, exactly as R16 shipped it, for comparison runs.
 */
export type Edition = "full" | "dealdesk";

export function edition(): Edition {
  const e = (process.env.NEXT_PUBLIC_CP_EDITION ?? "dealdesk").trim().toLowerCase();
  return e === "full" ? "full" : "dealdesk";
}

/** Where every removed route goes in the Deal Desk edition. The landing page after sign-in is the Cockpit ("/"). */
export const DEALDESK_HOME = "/deal-desk";

/** Routes the Deal Desk edition removes (path prefixes), each to DEALDESK_HOME. */
export const DEALDESK_EDITION_REMOVED: readonly string[] = [
  "/brf", "/lenses", "/early-warning", "/playbooks", "/stress", "/what-if", "/borrower-360",
  "/scorecard-validation", "/engine-builder", "/analysis", "/intelligence", "/queries", "/accepted-risk",
];

/** Where a link should go now: a removed screen's route becomes its redirect target; anything else is unchanged. */
export function liveHref(href: string): string {
  const path = href.split(/[?#]/)[0];
  if (edition() === "dealdesk") {
    if (DEALDESK_EDITION_REMOVED.some((p) => path === p || path.startsWith(p + "/"))) return DEALDESK_HOME;
    return href;
  }
  return REMOVED_ROUTES[path] ?? href;
}

export const NAV_ITEMS: NavItem[] = [
  {
    href: "/",
    label: "Cockpit",
    description:
      "Ask a question in plain language. CreditProbe AI plans the investigation, runs certified analyses and explains the result.",
    icon: Sparkles,
    status: "live",
    phase: "",
    group: "Home",
    demo: "core",
  },


  // ---- PLAN_R9: the intelligence shell. Session G owns this file and the sidebar. ----
  {
    href: "/brf",
    label: "BRF",
    description:
      "P7 BRF mapping: the CBUAE Banking Return Forms produced from the books, every cell mapped to its source and reconciled.",
    icon: FileSpreadsheet,
    status: "live",
    phase: "",
    group: "Intelligence",
    demo: "core",
  },

  // ---- WORK: the product hierarchy, largest container first ----
  {
    href: "/workspace",
    label: "Workspace",
    description:
      "Your home page: tasks and assignments, mentions, unread mail, reports awaiting your review, Early Warning on your books, and your analyses, investigations and projects.",
    icon: Inbox,
    status: "live",
    phase: "",
    group: "Work",
    demo: "core",
  },
  {
    href: "/messages",
    label: "Mail",
    description:
      "CreditProbe Mail: internal email with folders, labels, attachments and CreditProbe objects (answers, attention items, Early Warning lists, borrowers, What-If scenarios, reports) that open in place.",
    icon: MessagesSquare,
    status: "live",
    phase: "",
    group: "Work",
    demo: "core",
  },
  {
    href: "/projects",
    label: "Projects",
    description:
      "The master workspace. A Project holds investigations, saved analyses, documents, people and context.",
    icon: Boxes,
    status: "live",
    phase: "",
    group: "Work",
    demo: "core",
  },
  {
    href: "/investigations",
    label: "Investigations",
    description:
      "Conversational threads. An Investigation holds every question, answer, analysis and interpretation in one continuing thread.",
    icon: Search,
    status: "live",
    phase: "",
    group: "Work",
    demo: "core",
  },
  {
    href: "/analyses",
    label: "Analyses",
    description:
      "Executed and saved analytical results, each with the data version, parameters and Trace that produced it.",
    icon: BarChart3,
    status: "live",
    phase: "",
    group: "Work",
    demo: "core",
  },
  {
    href: "/playbook",
    label: "Playbook",
    description:
      "Committee packs, risk committee reports, portfolio reviews, credit memos and scenario reports: start from a template or an upload, let the assistant draft and import work from across CreditProbe with its charts and tables, track review and approval, and export a styled Word document.",
    icon: BookOpenCheck,
    status: "live",
    phase: "",
    group: "Work",
    demo: "core",
  },
  {
    href: "/policy-docs",
    label: "Policy Docs",
    description:
      "The bank's credit policies and circulars, stored with their clauses. Add a policy or circular: CreditProbe interprets it and, once approved, its clauses join the versioned policy pack the Cockpit cites.",
    icon: FileText,
    status: "live",
    phase: "",
    group: "Work",
    demo: "core",
  },

  // ---- INTELLIGENCE: standing capability rather than one-off work ----
  {
    href: "/lenses",
    label: "Lenses",
    description:
      "Live dashboards you build by asking: a KPI row, 8-14 charts, top names and a commentary on the corporate or retail book, each figure a query with its trace; edit by conversation or by hand, save, share, add to a Playbook report, export.",
    icon: LayoutGrid,
    status: "live",
    phase: "",
    group: "Intelligence",
    demo: "optional",
    demoNote:
      "Real and seeded with one published Lens. Shown if time allows; not on the twenty-minute path.",
  },
  {
    href: "/early-warning",
    label: "Early Warning",
    description:
      "v5 module 1. Corporate (sector, sub-sector, borrower) and Retail (product, Salaried/Non-Salaried, sub-product, customer), on the Early Warning service's own data aligned to the Cockpit books: who is warned, why, how it moved, and every rule evaluated on every exposure.",
    icon: Radar,
    status: "live",
    phase: "",
    group: "Intelligence",
    demo: "core",
  },
  {
    href: "/playbooks",
    label: "Playbooks",
    description:
      "A standing instruction: run these certified analyses over this scope, check these thresholds, and act when one is crossed. A run that finds nothing says so.",
    icon: ClipboardCheck,
    status: "partial",
    phase: "Manual and on-publication triggers run; scheduled ones are not yet wired to a scheduler",
    group: "Intelligence",
    demo: "optional",
    demoNote:
      "Manual and on-publication triggers run. Scheduled ones are not wired to a scheduler, so do not promise scheduling.",
  },
  {
    href: "/stress",
    label: "Stress Testing",
    description:
      "Named, versioned management scenarios applied to the portfolio, with comparison.",
    icon: FlaskConical,
    status: "live",
    phase: "",
    group: "Intelligence",
    demo: "optional",
  },

  // ---- DATA (PLAN_R6 B5, was BUILD): what the product is capable of, and what it may read ----
  {
    href: "/what-if",
    label: "What-If",
    description:
      "Conversational What-If: describe a scenario in plain words (PD, LGD, CCF, rating, sector stress, Saudi macro variables) for the whole book, a segment, a borrower, a facility or an Early Warning cohort; Delta method or XGBoost, with an exact ECL decomposition, likelihood, saved scenarios and a Word report.",
    icon: FlaskConical,
    status: "live",
    phase: "",
    group: "Intelligence",
    demo: "core",
  },
  {
    href: "/deal-desk",
    label: "Deal Desk",
    description:
      "Pre-deal analysis: a credit proposal measured against the RAROC hurdle, risk appetite and regulatory limits on the live corporate book, restructured into the counter-offer closest to the client's ask, with the maximum-value structure, the frontier between them, stress, the approval level and a Word report.",
    icon: Handshake,
    status: "live",
    phase: "",
    group: "Intelligence",
    demo: "core",
  },
  {
    href: "/borrower-360",
    label: "Borrower 360",
    description:
      "One borrower or customer on the books (Corporate/Retail): profile, facilities, exposure and ECL, ratings in the global order, stage and DPD, collateral, covenants, financials, group, Early Warning signals from every source, Bureau, Open Banking and notes, each tab exportable to Excel.",
    icon: Network,
    status: "live",
    phase: "",
    group: "Intelligence",
    demo: "core",
  },
  {
    href: "/scorecard-validation",
    label: "Scorecard",
    description:
      "Validate the retail application, retail behavioural and SME scorecards: choose a scorecard, agree the plan with the assistant, run discrimination, calibration, stability, variable and override tests against stated thresholds, review the red, amber and green verdicts, and produce the Word validation report for Playbook.",
    icon: Gauge,
    status: "live",
    phase: "",
    group: "Intelligence",
    demo: "core",
  },
  {
    href: "/studio",
    label: "Analysis Studio",
    description:
      "Every credit-risk method CreditProbe knows, what each one measures, and — where one exists — the implementation and the validation cases that prove it. Build new methods by describing them; certify them only once their validation pack passes.",
    icon: FlaskConical,
    status: "live",
    phase: "",
    group: "Data",
    demo: "core",
  },
  {
    href: "/data-builder",
    label: "Data Domains",
    description:
      "Browse every data domain read-only -- Cockpit books, Early Warning, Bureau and Open Banking: search, filter, compare two periods, export CSV/Excel, and the data dictionary.",
    icon: Database,
    status: "live",
    phase: "",
    group: "Data",
    demo: "core",
  },

  // ---- GOVERN ----
  {
    href: "/trace",
    label: "Trace & Lineage",
    description:
      "How an analysis was created: every step from question to chart, inspectable and modifiable.",
    icon: GitBranch,
    status: "live",
    phase: "",
    group: "Govern",
    demo: "core",
  },
  {
    href: "/workflow",
    label: "Workflow",
    description:
      "Share, review and approve the things that carry institutional weight, with an append-only decision history.",
    icon: ClipboardCheck,
    status: "live",
    phase: "",
    group: "Admin",
    demo: "admin",
  },

  // ---- ADMIN ----
  {
    href: "/agent-operations",
    label: "Agent Operations",
    description:
      "The governed agentic layer: the twelve specialists and what each may do, every run and what it cost, the schedules, the policies, the approvals waiting for a person, and how the agents score against the evaluation corpus.",
    icon: Bot,
    status: "live",
    phase: "",
    group: "Admin",
    demo: "admin",
    demoNote:
      "Already restricted to ADMIN and DATA_STEWARD. Compelling to a technical audience and irrelevant to a CRO.",
    // §64: "Only authorized roles can access it." §28 places it with
    // Administration rather than in the ordinary Cockpit navigation, because
    // an analyst has no use for a worker heartbeat.
    roles: ["ADMIN", "DATA_STEWARD"],
  },
  {
    href: "/ai-studio",
    label: "AI Studio",
    description:
      "What CreditProbe has been taught, how it was validated, how it is performing, what has gone stale and which release is running \u2014 for the ontology, the teaching library, the investigation blueprints, the judgment policies, the visualization grammar and the model routing.",
    icon: Brain,
    status: "live",
    phase: "",
    group: "Admin",
    demo: "admin",
    demoNote:
      "Already restricted to ADMIN and DATA_STEWARD. Holds the Feedback & Learning area, which is worth showing on request rather than by default.",
    // §119: an ordinary Analyst sees only a compact assurance badge on the
    // answer itself. Reading which cases production retrieves is most of the
    // way to knowing how to phrase a question to get a chosen answer, so the
    // Studio needs the standing to change it — and every endpoint behind it
    // enforces that whatever the sidebar shows.
    roles: ["ADMIN", "DATA_STEWARD"],
  },
  {
    href: "/users",
    label: "Users & Teams",
    description: "Users, teams, roles and permissions at capability, object and data level.",
    icon: Users,
    status: "preview",
    phase: "Placeholder records",
    group: "Admin",
    // Restricted here in the release-candidate phase. The route crawl found
    // an ANALYST and a VIEWER seeing this link and getting a 403 from
    // `/api/v1/users` the moment they clicked it — the sidebar was offering
    // a door the API was always going to refuse. The endpoint's permission
    // was right; the invitation was wrong.
    roles: ["ADMIN"],
    demo: "admin",
    demoNote:
      "Real accounts and real permissions, but the screen is labelled Preview and its team management is not complete.",
  },
  {
    href: "/settings",
    label: "Settings",
    description: "Themes, roles, model configuration and administration.",
    icon: Settings,
    status: "partial",
    phase: "",
    group: "Admin",
    demo: "admin",
  },
  {
    href: "/audit-log",
    label: "Audit log",
    description:
      "Who did what and when: sign-ins, exports, approvals, configuration changes and AI runs, filterable and exportable.",
    icon: ScrollText,
    status: "live",
    phase: "",
    group: "Admin",
    demo: "admin",
  },
];

export const STATUS_LABEL: Record<CapabilityStatus, string> = {
  live: "Live",
  partial: "Partial",
  preview: "Preview",
  planned: "Planned",
};

/**
 * v5: the modules that run in this build, in the order they are delivered.
 *
 * A v5 runtime (the frozen Cockpit's V4 API is configured) lists only these:
 * every other page in NAV_ITEMS calls a backend v5 does not run, and a
 * sidebar of empty screens is worse than a short one. Borrower 360 and
 * What-If join this list when their modules are built and accepted.
 */
export const V5_LIVE_HREFS: readonly string[] = [
  // Home (PLAN_R10 S1: the Cockpit is the landing page after sign-in)
  "/",
  // Intelligence
  "/early-warning", "/borrower-360", "/what-if", "/lenses", "/deal-desk", "/scorecard-validation", "/brf",
  // Work (Workspace stays reachable here and from the user menu); Deal Desk is under Intelligence (PLAN_R10)
  "/workspace", "/messages", "/playbook", "/policy-docs", "/projects", "/investigations", "/analyses",
  // Data
  "/data-builder",
  // Admin, at the bottom (PLAN_R5 P1, the pages are Session A's)
  "/workflow", "/users", "/agent-operations", "/ai-studio", "/settings", "/audit-log",
];

/**
 * The Deal Desk edition's sidebar: the Cockpit (the landing page; its brief and Ask are Deal Desk's), Deal Desk, then
 * the Work group, Data (Data Domains and Analysis Studio), Trace, and Admin at the bottom.
 */
export const DEALDESK_EDITION_HREFS: readonly string[] = [
  // Home: the Cockpit, the landing page after sign-in
  "/",
  // Intelligence: Deal Desk is the product
  "/deal-desk",
  // Work
  "/workspace", "/messages", "/playbook", "/policy-docs", "/projects", "/investigations", "/analyses",
  // Data
  "/data-builder", "/studio",
  // Govern
  "/trace",
  // Admin
  "/workflow", "/users", "/agent-operations", "/ai-studio", "/settings", "/audit-log",
];

/** The hrefs this build lists, by edition. */
export function liveHrefs(): readonly string[] {
  return edition() === "dealdesk" ? DEALDESK_EDITION_HREFS : V5_LIVE_HREFS;
}

/** The v5 sidebar order is the order of the edition's href list, whatever the order of NAV_ITEMS. */
function v5Order(a: NavItem, b: NavItem): number {
  const live = liveHrefs();
  return live.indexOf(a.href) - live.indexOf(b.href);
}

function v5Runtime(): boolean {
  return Boolean(process.env.NEXT_PUBLIC_COCKPIT_V4_API?.trim());
}

export function itemsInGroup(
  group: NavGroup,
  role?: string,
  demoMode = false,
  isAdmin = true,
): NavItem[] {
  // The Deal Desk edition lists its own hrefs whatever the runtime; the full product lists them in a v5 runtime.
  const v5 = v5Runtime() || edition() === "dealdesk";
  const live = liveHrefs();
  // PLAN_R5 P1: in v5 the Admin group is for administrators (the v5 identity's is_admin), at the bottom.
  if (v5 && group === "Admin" && !isAdmin) return [];
  const items = NAV_ITEMS.filter(
    (item) =>
      item.group === group &&
      (!v5 || live.includes(item.href)) &&
      (!item.roles || !role || item.roles.includes(role)) &&
      // In Demo Mode, `hidden` items leave the navigation. Out of it, every
      // capability is listed with its honest status, which is what a
      // development build and a pilot both want.
      !(demoMode && item.demo === "hidden"),
  );
  return v5 ? items.sort(v5Order) : items;
}

/** Everything in one demo scope, for the scope-freeze document and its test. */
export function itemsInDemoScope(scope: DemoScope): NavItem[] {
  return NAV_ITEMS.filter((item) => item.demo === scope);
}

export function findNavItem(href: string): NavItem | undefined {
  return NAV_ITEMS.find((item) => item.href === href);
}
