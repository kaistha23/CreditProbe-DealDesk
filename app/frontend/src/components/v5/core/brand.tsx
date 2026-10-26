/**
 * Quantalpha Advisory brand (PLAN_R6 B2, B3).
 *
 * The wordmark is rebuilt from `public/brand/quantalpha_logo_source.png`: a
 * book serif "Quant", a blue italic alpha, then "lpha". The source is black on
 * white; here the serif letters take `currentColor`, so the mark reads in the
 * Executive Ivory light theme and in dark, and only the alpha keeps the brand
 * blue (lightened a step in dark so it holds its contrast on navy).
 *
 * Proportions from the source (436 x 76 px crop): cap height about 62% of the
 * box, the alpha sits on the baseline at x-height, letter spacing tight.
 */
import * as React from "react";

export const QUANTALPHA_BLUE = "#1f2bd6";
export const QUANTALPHA_BLUE_DARK = "#7f8cff";

const SERIF = "'Times New Roman', Times, 'Liberation Serif', 'Nimbus Roman', Georgia, serif";

/** The full Quantalpha wordmark. `height` sets the rendered height in px; width follows the 4.6:1 ratio. */
export function QuantalphaLogo({ height = 28, className, title = "Quantalpha Advisory" }: {
  height?: number;
  className?: string;
  title?: string;
}) {
  return (
    <svg
      viewBox="0 0 230 50"
      height={height}
      width={(height * 230) / 50}
      role="img"
      aria-label={title}
      data-testid="quantalpha-logo"
      className={className}
    >
      <title>{title}</title>
      <text
        x="0"
        y="40"
        fontFamily={SERIF}
        fontSize="48"
        fill="currentColor"
        letterSpacing="-0.6"
      >
        Quant
        <tspan className="quantalpha-alpha" fontStyle="italic" fill={QUANTALPHA_BLUE} dx="1">α</tspan>
        <tspan dx="0.5">lpha</tspan>
      </text>
    </svg>
  );
}

/** The small mark for the header: the blue italic alpha on its own, sized to the wordmark's cap height. */
export function QuantalphaMark({ size = 14 }: { size?: number }) {
  return (
    <svg viewBox="0 0 20 20" width={size} height={size} aria-hidden data-testid="quantalpha-mark">
      <text x="10" y="15.5" textAnchor="middle" fontFamily={SERIF} fontSize="20" fontStyle="italic" className="quantalpha-alpha" fill={QUANTALPHA_BLUE}>α</text>
    </svg>
  );
}

/**
 * The header lockup: "CreditProbe AI", a hairline divider, "by", and the
 * Quantalpha wordmark at the same cap height, all on one baseline.
 */
export function HeaderLockup() {
  return (
    <span className="flex items-center gap-2.5" data-testid="header-lockup">
      <span className="text-[14px] font-semibold leading-none tracking-[0.02em] text-text-primary">
        CreditProbe<span className="ml-1 text-accent">AI</span>
      </span>
      <span aria-hidden className="h-4 w-px bg-border" />
      <span className="flex items-center gap-1.5 text-text-muted">
        <span className="text-[11px] leading-none">by</span>
        <QuantalphaLogo height={15} className="text-text-primary" />
      </span>
    </span>
  );
}

