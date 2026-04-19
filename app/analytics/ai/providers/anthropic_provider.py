import anthropic

from app.analytics.ai.provider import AIProvider, AIResponse
from app.exceptions import AIProviderError

# Cost per million tokens (USD)
_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
}


class AnthropicProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self._model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "anthropic"

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
        # For JSON mode: inject instruction into system prompt (Anthropic has no native JSON mode)
        effective_system = system_prompt
        if response_format == "json":
            effective_system = system_prompt + "\n\nReturn ONLY valid JSON. No explanation, no markdown."

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=effective_system,
                messages=[{"role": "user", "content": user_prompt}],
            )
            content = response.content[0].text if response.content else ""
            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens

            return AIResponse(
                content=content,
                model=self._model,
                provider="anthropic",
                tokens_input=tokens_in,
                tokens_output=tokens_out,
                cost_usd=self.estimate_cost(tokens_in, tokens_out),
            )
        except anthropic.APIError as exc:
            raise AIProviderError("anthropic", self._model, str(exc), getattr(exc, "status_code", None)) from exc

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing = _PRICING.get(self._model, {"input": 0.0, "output": 0.0})
        return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
