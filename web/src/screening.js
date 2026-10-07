/** One-line status of the RedTeamGPT prompt screening. */
export function screeningLabel(guard) {
  return {
    clean: "RedTeamGPT: clean",
    flagged: "RedTeamGPT: injection flagged",
    unavailable: "RedTeamGPT unreachable (LLM skipped)",
  }[guard?.status] || "Off";
}

