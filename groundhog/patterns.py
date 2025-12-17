DEFAULT_PATTERN = "No pattern"

PATTERNS = {
    DEFAULT_PATTERN: "",
    "Plan Day": "Based on the provided notes, create a detailed plan for my day.",
    "Analyse My Day": "Based on the provided notes, analyze my day and give me feedback.",
    "Summarize Notes": "Summarize the key points from the provided notes in a few sentences.",
    "Identify People": "List all the people mentioned in the provided notes.",
    "Extract Actions": "Extract all action items or tasks from the provided notes.",
}


def list_patterns() -> list[str]:
    ordered = [DEFAULT_PATTERN]
    ordered.extend([name for name in PATTERNS.keys() if name != DEFAULT_PATTERN])
    return ordered


