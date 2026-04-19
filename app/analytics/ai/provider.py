"""
Abstract AI provider interface.
"""
from abc import ABC, abstractmethod

from pydantic import BaseModel


class AIResponse(BaseModel):
    content: str
    model: str
    provider: str
    tokens_input: int
    tokens_output: int
    cost_usd: float


class AIProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...

    @abstractmethod
    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        response_format: str = "json",
    ) -> AIResponse:
        ...

    async def analyze_batch(
        self,
        prompts: list[dict],
        temperature: float = 0.0,
    ) -> list[AIResponse]:
        """Default: sequential calls. Providers can override with native batch APIs."""
        results = []
        for p in prompts:
            result = await self.analyze(
                system_prompt=p.get("system", ""),
                user_prompt=p.get("user", ""),
                temperature=temperature,
            )
            results.append(result)
        return results

    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        ...
