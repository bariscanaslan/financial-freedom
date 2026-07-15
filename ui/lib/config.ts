// Environment config. Base URL from env; no hardcoding (only a sensible local
// default for development).

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8089";

// Guide threshold: a skill_score below this "does not meaningfully beat naive".
export const MIN_SKILL = 0.01;
