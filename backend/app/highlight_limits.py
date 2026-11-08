"""Frame-based limits for new highlight approvals and automatic Mix."""

MIN_FRAMES = 300
MAX_FRAMES = 36000
RULES_VERSION = 1


class MixBudget:
    def __init__(self, length, maximum=None):
        self.windows = [
            {"start": a, "end": min(a + 1800, length), "used": 0, "count": 0}
            for a in range(0, length, 1800)
        ]
        self.maximum = maximum or 5

    def accept(self, start, end):
        owner = next(w for w in self.windows if w["start"] <= start < w["end"])
        cap = min(self.maximum, 5, ((owner["end"] - owner["start"]) * 3 // 10) // 90)
        if owner["count"] >= cap:
            return False
        coverage = [max(0, min(end, w["end"]) - max(start, w["start"])) for w in self.windows]
        if any(
            w["used"] + n > (w["end"] - w["start"]) * 3 // 10
            for w, n in zip(self.windows, coverage)
        ):
            return False
        owner["count"] += 1
        for w, n in zip(self.windows, coverage):
            w["used"] += n
        return True
