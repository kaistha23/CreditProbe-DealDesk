/**
 * PLAN_R13 §I Session IC: network and events — one compact panel per engine, and the tools menu that opens them.
 *
 *   Borrower 360 (customer page)  <NetworkToolsMenu module="b360" borrowerId={id} borrowerName={name} period={p} />
 *   What-If (home header)         <NetworkToolsMenu module="whatif" />
 *   Noor intents                  frontend/src/lib/v5/intel-intents-ic.ts (IC_INTENTS) -> networkApi + these panels
 */
export { EventTranslatorPanel, EventView } from "./event-panel";
export { ContagionPanel, ContagionView } from "./contagion-panel";
export { EmployerPanel, EmployerView, RankingView } from "./employer-panel";
export { NETWORK_TOOLS, NetworkToolPanel, NetworkToolsMenu, toolsFor } from "./tools-menu";
export type { NetworkModule, NetworkTool, NetworkToolId } from "./tools-menu";
export { networkApi, NETWORK_PREFIX } from "./api";
export type { ContagionResult, EmployerRanking, EmployerResult, EventCatalogue, EventRequest, EventResult } from "./format";
