import openai

from app.analytics.ai.provider import AIProvider, AIResponse
from app.exceptions import AIProviderError

# GPT-5+ family uses `max_completion_tokens`; older models use `max_tokens`.
_MAX_COMPLETION_TOKENS_MODELS: frozenset[str] = frozenset({
    "gpt-5", "gpt-5-mini", "gpt-5-nano",
    "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano",
})

# Cost per million tokens (USD). Verified May 2026.
_PRICING: dict[str, dict[str, float]] = {
    # GPT-4 (legacy)
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 5.00, "output": 15.00},
    # GPT-5 family
    "gpt-5-nano": {"input": 0.05, "output": 0.40},
    "gpt-5-mini": {"input": 0.40, "output": 1.60},
    "gpt-5": {"input": 2.50, "output": 15.00},
    # GPT-5.4 family (current, March 2026)
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gpt-5.4": {"input": 2.50, "output": 15.00},
}


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self._model = model
        self._client = openai.AsyncOpenAI(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        response_format: str = "json",
    ) -> AIResponse:
        try:
            kwargs: dict = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                ("max_completion_tokens" if self._model in _MAX_COMPLETION_TOKENS_MODELS else "max_tokens"): max_tokens,
                "seed": 42,
            }
            if response_format == "json":
                kwargs["response_format"] = {"type": "json_object"}

            response = await self._client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            tokens_in = response.usage.prompt_tokens if response.usage else 0
            tokens_out = response.usage.completion_tokens if response.usage else 0

            return AIResponse(
                content=content,
                model=self._model,
                provider="openai",
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                cost_usd=self.estimate_cost(tokens_in, tokens_out),
            )
        except openai.APIError as exc:
            raise AIProviderError("openai", self._model, str(exc), getattr(exc, "status_code", None)) from exc

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing = _PRICING.get(self._model, {"input": 0.0, "output": 0.0})
        return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
