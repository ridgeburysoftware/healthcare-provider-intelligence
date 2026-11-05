"""Server-side selection for optional explanations; analytics do not depend on AI."""
import os


def ai_status():
    provider = os.getenv("AI_PROVIDER", "openai").strip().lower()
    key = "OPENAI_API_KEY" if provider == "openai" else "BEDROCK_MODEL_ID"
    available = provider in {"openai", "bedrock"} and bool(os.getenv(key, "").strip())
    return {"ai_provider": provider if provider in {"openai", "bedrock"} else None,
            "ai_available": available}


def explain(context):
    if ai_status()["ai_provider"] == "bedrock":
        from .llm_bedrock import explain_with_bedrock
        return explain_with_bedrock(context)
    from .llm_openai import explain_with_openai
    return explain_with_openai(context)
