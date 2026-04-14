from app.analytics.ai.provider import AIProvider
from app.config import settings
from app.exceptions import ValidationError


def create_provider() -> AIProvider:
    """
    Return the configured AI provider instance.
    Provider is selected via AI_PROVIDER env var.
    """
    provider_name = settings.ai_provider.lower()
    model = settings.ai_model

    if provider_name == "openai":
        if not settings.openai_api_key:
            raise ValidationError("OPENAI_API_KEY", "OpenAI API key is required when AI_PROVIDER=openai")
        from app.analytics.ai.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=settings.openai_api_key, model=model)

    elif provider_name == "anthropic":
        if not settings.anthropic_api_key:
            raise ValidationError("ANTHROPIC_API_KEY", "Anthropic API key is required when AI_PROVIDER=anthropic")
        from app.analytics.ai.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=settings.anthropic_api_key, model=model)

    elif provider_name == "gemini":
        if not settings.gemini_api_key:
            raise ValidationError("GEMINI_API_KEY", "Gemini API key is required when AI_PROVIDER=gemini")
        from app.analytics.ai.providers.gemini_provider import GeminiProvider
        return GeminiProvider(api_key=settings.gemini_api_key, model=model)

    elif provider_name == "mock":
        from app.analytics.ai.providers.mock_provider import MockProvider
        return MockProvider()

    else:
        raise ValidationError("AI_PROVIDER", f"Unknown provider '{provider_name}'. Choose: openai, anthropic, gemini, mock")
