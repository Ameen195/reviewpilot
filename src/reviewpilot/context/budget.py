# Groq free tier is ~8K tokens/minute per model, so one request must stay well under that.
MAX_FILE_TOKENS = 4_000
MAX_PR_TOKENS = 20_000


def est_tokens(text: str) -> int:
    return (
        len(text) // 4 + 1
    )  # shortcut: ~4 chars/token, no tokenizer; swap for a real one if limits bite
