from google import genai
from google.genai import types

from app.analytics.ai.provider import AIProvider, AIResponse
from app.exceptions import AIProviderError

# Cost per million tokens (USD)
_PRICING: dict[str, dict[str, float]] = {
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
}


class GeminiProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self._model = model
        self._client = genai.Client(api_key=api_key)

    @property
    def provider_name(self) -> str:
        return "gemini"

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
        effective_system = system_prompt
        if response_format == "json":
            effective_system = system_prompt + "\n\nReturn ONLY valid JSON. No explanation, no markdown."

        try:
            config = types.GenerateContentConfig(
                system_instruction=effective_system,
                temperature=temperature,
                top_k=1,
                max_output_tokens=max_tokens,
                response_mime_type="application/json" if response_format == "json" else "text/plain",
            )

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
            if "flash-lite" in model_lower:
                pricing = {"input": 0.075, "output": 0.30}
            elif "flash" in model_lower:
                pricing = {"input": 0.10, "output": 0.40}
            elif "pro" in model_lower:
                pricing = {"input": 1.25, "output": 5.00}
            else:
                pricing = {"input": 0.10, "output": 0.40}
        return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
