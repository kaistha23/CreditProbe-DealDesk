/**
 * The shared answer renderer (PLAN_R12 N2). Import from "@/components/answer". The Plotly theme is
 * "@/lib/plotly-theme"; `Plot` (the one Plotly surface) is re-exported here for convenience.
 */
export { Answer, AnswerFrame, type AnswerTableData } from "./answer";
export { AnswerChart, type AnswerChartBlock, answerFigure, seriesHover } from "./chart";
export { AnswerChips, type AnswerChip, chipSlug } from "./chips";
export { AnswerFigures, type AnswerFigure } from "./figures";
export { AnswerHeadline, AnswerProse, inline as answerInline, prepare as prepareAnswerText } from "./prose";
export { AnswerTable, type AnswerColumn, looksNumeric } from "./table";
export { A as ANSWER_STYLE } from "./styles";
export { TOOL_PHRASES, bankerChips, bankerLabel, bankerText, hasInternalName, type BankerChip } from "./banker";
export { figuresIn, foldProse, plainHeadline, splitHeadline } from "./headline";
export { PlotlySpark, useNearViewport } from "./spark";
export { hbarFigure, shareBarFigure } from "./bar-figure";
export { Plot } from "@/components/v5/ews/plot";
