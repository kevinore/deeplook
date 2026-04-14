"""
Track AI usage costs per client/job.
"""
from dataclasses import dataclass, field


@dataclass
class CostTracker:
    total_tokens_input: int = 0
    total_tokens_output: int = 0
    total_cost_usd: float = 0.0
    call_count: int = 0
    failed_calls: int = 0

    def record(self, tokens_input: int, tokens_output: int, cost_usd: float) -> None:
        self.total_tokens_input += tokens_input
        self.total_tokens_output += tokens_output
        self.total_cost_usd += cost_usd
        self.call_count += 1

    def record_failure(self) -> None:
        self.failed_calls += 1

    @property
    def total_tokens(self) -> int:
        return self.total_tokens_input + self.total_tokens_output

    def summary(self) -> dict:
        return {
            "calls": self.call_count,
            "failed_calls": self.failed_calls,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
        }
