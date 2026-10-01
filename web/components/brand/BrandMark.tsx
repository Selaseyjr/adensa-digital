/**
 * The Adensa brand mark (Visual Identity v1).
 *
 * Concept: A + light + continuity. A triangular apex ("A",
 * daylight breaking) over three horizon lines of descending
 * weight — continuous day, the Akan naming idea behind the
 * name, read equally as flow lines / a network pathway.
 * Pure geometry, stroke-built: no truck, globe, package,
 * container, arrow or sparkle.
 *
 * Architecture rules:
 * - This component is the ONLY place the mark's SVG lives.
 *   Nothing else in the app should embed mark geometry.
 * - The mark is replaceable: swap the geometry inside the
 *   two <svg> blocks and every consumer updates at once.
 * - It inherits colour from context (currentColor) so the
 *   same geometry works on light chrome, the dark Command
 *   Centre, and monochrome print/documentation contexts.
 * - `AdensaMarkIcon` is the compact standalone form used as
 *   the application icon / favicon source.
 */

interface BrandMarkProps {
  /** Rendered size in px (square); defaults to 30. */
  size?: number;
  /** Hide from the accessibility tree when the adjacent
      "Adensa Digital" text already names the brand. */
  decorative?: boolean;
  className?: string;
}

export function BrandMark({
  size = 30,
  decorative = true,
  className,
}: BrandMarkProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      className={className ?? "app-brand-mark"}
      aria-hidden={decorative || undefined}
      role={decorative ? undefined : "img"}
      focusable="false"
    >
      {/* The apex: an open "A" — daylight breaking, not a
          closed triangle. Strokes inherit currentColor. */}
      <path
        d="M6 21 16 5l10 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Horizon: continuous day — three lines of descending
          weight, the rhythm of a network carrying flow. */}
      <path
        d="M9 24h14"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <path
        d="M11 27.5h10"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        opacity="0.65"
      />
      <path
        d="M13 31h6"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
        opacity="0.4"
      />
    </svg>
  );
}

/**
 * Compact standalone icon form (application icon, favicon
 * source): the same concept closed into a self-contained
 * navy tile so it holds up at 16px without context.
 */
export function AdensaMarkIcon({ size = 32 }: { size?: number }) {
  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      role="img"
      aria-label="Adensa Digital"
      focusable="false"
    >
      <rect width="32" height="32" rx="6" fill="#0b1f33" />
      {/* Apex + horizon in the light accent — day on navy. */}
      <path
        d="M8 20.5 16 7l8 13.5"
        fill="none"
        stroke="#85b8e8"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M10.5 24h11"
        stroke="#f2f6fa"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
      <path
        d="M12.5 27.5h7"
        stroke="#f2f6fa"
        strokeWidth="1.4"
        strokeLinecap="round"
        opacity="0.6"
      />
    </svg>
  );
}
