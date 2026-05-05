from google import genai
from google.genai import types

from app.analytics.ai.provider import AIProvider, AIResponse
from app.exceptions import AIProviderError

# Cost per million tokens (USD). Verified May 2026.
_PRICING: dict[str, dict[str, float]] = {
    # Gemini 1.x (legacy)
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    # Gemini 2.x (legacy)
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    # Gemini 3.x (current)
    "gemini-3-flash-lite": {"input": 0.25, "output": 1.50},
    "gemini-3.1-flash-lite-preview": {"input": 0.25, "output": 1.50},
    "gemini-3-flash": {"input": 0.50, "output": 2.00},
    "gemini-3-pro": {"input": 1.25, "output": 10.00},
}

# Models that support native chain-of-thought "thinking" config.
# Enabling thinking improves calibration on subjective scoring tasks
# (sentiment, quality breakdown) at the cost of a few extra output tokens.
_THINKING_CAPABLE_PREFIXES = ("gemini-3",)


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-lite-preview"):
        self._model = model
        self._client = genai.Client(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def _supports_thinking(self) -> bool:
        return any(self._model.startswith(p) for p in _THINKING_CAPABLE_PREFIXES)

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        response_format: str = "json",
    ) -> AIResponse:
        effective_system = system_prompt
        if response_format == "json":
            effective_system = (
                system_prompt
                + "\n\nIMPORTANTE: Devuelve EXCLUSIVAMENTE un objeto JSON válido en español. "
                "Sin texto adicional, sin markdown, sin ```json."
            )

        config_kwargs: dict = {
            "system_instruction": effective_system,
            "temperature": temperature,
            "top_k": 1,
            "max_output_tokens": max_tokens,
            "response_mime_type": "application/json" if response_format == "json" else "text/plain",
        }

        # Enable native reasoning on Gemini 3.x to improve scoring consistency.
        # ThinkingConfig may not be present in older SDK versions — degrade gracefully.
        if self._supports_thinking():
            try:
                config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=1024)
            except (AttributeError, TypeError):
                pass

        try:
            config = types.GenerateContentConfig(**config_kwargs)

            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=config,
            )

            content = response.text or ""
            tokens_in = response.usage_metadata.prompt_token_count or 0
            tokens_out = response.usage_metadata.candidates_token_count or 0

            return AIResponse(
                content=content,
                model=self._model,
                provider="gemini",
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                cost_usd=self.estimate_cost(tokens_in, tokens_out),
            )

        except Exception as exc:
            raise AIProviderError("gemini", self._model, str(exc)) from exc

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing = _PRICING.get(self._model)
        if pricing is None:
            # Prefix-based fallback for preview / unreleased models
            model_lower = self._model.lower()
            if "3" in model_lower and "flash-lite" in model_lower:
                pricing = {"input": 0.25, "output": 1.50}
            elif "3" in model_lower and "flash" in model_lower:
                pricing = {"input": 0.50, "output": 2.00}
            elif "3" in model_lower and "pro" in model_lower:
                pricing = {"input": 1.25, "output": 10.00}
            elif "flash-lite" in model_lower:
                pricing = {"input": 0.075, "output": 0.30}
            elif "flash" in model_lower:
                pricing = {"input": 0.10, "output": 0.40}
            elif "pro" in model_lower:
                pricing = {"input": 1.25, "output": 5.00}
            else:
                pricing = {"input": 0.10, "output": 0.40}
        return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
