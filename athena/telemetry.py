"""Runtime telemetry: every pipeline stage is timed, and LLM token/cost usage
(zero on the template fallback path) is tracked per run."""
import time
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class Telemetry:
    stage_ms: dict = field(default_factory=dict)
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0

    @contextmanager
    def stage(self, name):
        start = time.perf_counter()
        yield
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.stage_ms[name] = round(elapsed_ms, 3)

    def record_narrative(self, narrative_result):
        self.llm_calls += narrative_result["llm_calls"]
        self.tokens_in += narrative_result["tokens_in"]
        self.tokens_out += narrative_result["tokens_out"]
        self.cost_usd += narrative_result["cost_usd"]

    @property
    def total_ms(self):
        return round(sum(self.stage_ms.values()), 3)

    @property
    def deterministic_share_pct(self):
        non_narrative = sum(v for k, v in self.stage_ms.items() if k != "narrative")
        return round(100 * non_narrative / self.total_ms, 1) if self.total_ms else 0.0

    def summary(self):
        return {
            "stage_ms": self.stage_ms,
            "total_ms": self.total_ms,
            "deterministic_share_pct": self.deterministic_share_pct,
            "llm_calls": self.llm_calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 6),
        }
