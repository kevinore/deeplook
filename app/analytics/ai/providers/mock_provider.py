"""
Mock AI provider for testing. Returns deterministic results without API calls.
"""
import hashlib
import json

from app.analytics.ai.provider import AIProvider, AIResponse


def _hash_seed(text: str) -> int:
    return int(hashlib.md5(text.encode()).hexdigest(), 16)


class MockProvider(AIProvider):
    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-v1"

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        response_format: str = "json",
    ) -> AIResponse:
        seed = _hash_seed(user_prompt)
        sentiments = ["positive", "neutral", "negative"]
        sentiment = sentiments[seed % 3]
        topics = ["pricing", "appointment", "product inquiry", "complaint", "follow-up"]
        primary_topic = topics[seed % len(topics)]
        conversions = ["converted", "lost", "pending", "not_applicable"]
        conversion = conversions[seed % len(conversions)]
        quality = round(5.0 + (seed % 50) / 10, 1)

        result = {
            "sentiment": sentiment,
            "sentiment_score": round((seed % 200 - 100) / 100, 2),
            "sentiment_reason": f"The conversation showed {sentiment} signals based on customer tone.",
            "primary_topic": primary_topic,
            "secondary_topics": [topics[(seed + 1) % len(topics)]],
            "quality_score": quality,
            "quality_breakdown": {
                "helpfulness": round(quality + 0.5, 1),
                "tone": round(quality - 0.3, 1),
                "completeness": round(quality + 0.2, 1),
                "speed_perception": round(quality - 0.1, 1),
            },
            "conversion_status": conversion,
            "conversion_reason": f"Customer showed {conversion} signals.",
            "summary": "The customer inquired about services and received a response from the business.",
            "key_points": ["Customer asked about pricing", "Business responded promptly"],
        }

        return AIResponse(
            content=json.dumps(result),
            model="mock-v1",
            provider="mock",
            tokens_input=150,
            tokens_output=250,
            cost_usd=0.0,
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0
