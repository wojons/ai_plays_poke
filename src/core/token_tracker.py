"""Token usage tracker for API cost calculation."""

import threading
from datetime import datetime
from typing import Any, Dict, List


class TokenTracker:
    """Track token usage and calculate costs accurately"""

    def __init__(self) -> None:
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self.call_count = 0
        self.request_history: List[Dict[str, Any]] = []
        self.lock = threading.Lock()

    def record_request(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        duration_ms: float
    ) -> None:
        with self.lock:
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cost += cost
            self.call_count += 1

            self.request_history.append({
                "timestamp": datetime.now().isoformat(),
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
                "duration_ms": duration_ms
            })

    def get_cost_per_decision(self, decisions: int = 1) -> float:
        """Calculate cost per decision (accurate to $0.001)"""
        if decisions <= 0:
            return 0.0
        return float(self.total_cost / decisions)

    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        with self.lock:
            return {
                "total_calls": self.call_count,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_tokens": self.total_input_tokens + self.total_output_tokens,
                "total_cost": round(self.total_cost, 6),
                "avg_cost_per_call": round(self.total_cost / self.call_count, 6) if self.call_count > 0 else 0.0,
                "avg_input_tokens": round(self.total_input_tokens / self.call_count, 1) if self.call_count > 0 else 0,
                "avg_output_tokens": round(self.total_output_tokens / self.call_count, 1) if self.call_count > 0 else 0
            }

    def reset(self) -> None:
        with self.lock:
            self.total_input_tokens = 0
            self.total_output_tokens = 0
            self.total_cost = 0.0
            self.call_count = 0
            self.request_history = []
