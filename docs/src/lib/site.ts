/**
 * Soft-capped headline stats, kept in one place so the landing page copy never
 * drifts ahead of the codebase. Prefer lower bounds — never overstate.
 */
export const STATS = [
  { value: "150+", label: "public exports" },
  { value: "250+", label: "tests passing" },
  { value: "83%", label: "coverage" },
  { value: "40+", label: "docs pages" },
] as const
