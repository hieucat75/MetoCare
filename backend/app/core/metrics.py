"""Minimal in-process metrics with Prometheus text rendering (no dependency).

Counters + histograms only, enough for request rate/latency/error monitoring.
Use bounded label values (route templates, not raw paths) to avoid cardinality
blow-up. Exposed via /metrics, gated by MCP_METRICS_ENABLED.
"""

from __future__ import annotations

from collections import defaultdict

# Latency buckets in seconds (Prometheus convention).
_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _label_str(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in labels)
    return "{" + inner + "}"


class Metrics:
    def __init__(self) -> None:
        self._counters: dict[tuple, float] = defaultdict(float)
        self._hist_buckets: dict[tuple, dict[float, int]] = defaultdict(
            lambda: dict.fromkeys(_BUCKETS, 0)
        )
        self._hist_sum: dict[tuple, float] = defaultdict(float)
        self._hist_count: dict[tuple, int] = defaultdict(int)

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None) -> tuple:
        items = tuple(sorted((labels or {}).items()))
        return (name, items)

    def inc_counter(
        self, name: str, labels: dict[str, str] | None = None, value: float = 1
    ) -> None:
        self._counters[self._key(name, labels)] += value

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._key(name, labels)
        for b in _BUCKETS:
            if value <= b:
                self._hist_buckets[key][b] += 1
        self._hist_sum[key] += value
        self._hist_count[key] += 1

    def reset(self) -> None:
        self._counters.clear()
        self._hist_buckets.clear()
        self._hist_sum.clear()
        self._hist_count.clear()

    def render(self) -> str:
        lines: list[str] = []
        for (name, labels), val in sorted(self._counters.items()):
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name}{_label_str(labels)} {val:g}")
        for (name, labels), buckets in sorted(self._hist_buckets.items()):
            lines.append(f"# TYPE {name} histogram")
            cumulative = 0
            for b in _BUCKETS:
                cumulative += buckets[b]
                le_labels = labels + (("le", str(b)),)
                lines.append(f"{name}_bucket{_label_str(le_labels)} {cumulative}")
            inf_labels = labels + (("le", "+Inf"),)
            total = self._hist_count[(name, labels)]
            lines.append(f"{name}_bucket{_label_str(inf_labels)} {total}")
            lines.append(f"{name}_sum{_label_str(labels)} {self._hist_sum[(name, labels)]:g}")
            lines.append(f"{name}_count{_label_str(labels)} {self._hist_count[(name, labels)]}")
        return "\n".join(lines) + "\n"


registry = Metrics()
