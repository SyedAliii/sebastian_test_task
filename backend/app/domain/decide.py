from dataclasses import dataclass

from app.domain.labels import PROHIBITED


@dataclass(frozen=True)
class Decision:
    status: str
    hold_reason: str | None
    reasons: list[str]


def decide(frames: list, verified: bool) -> Decision:
    blocked: list[str] = []
    review: list[str] = []
    explicit_high = False
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        for label in PROHIBITED:
            score = _score(frame.get(label, 0))
            if score >= 0.8 and label not in blocked:
                blocked.append(label)
            elif score >= 0.5 and label not in review and label not in blocked:
                review.append(label)
        if _score(frame.get("explicit", 0)) >= 0.8:
            explicit_high = True
    if blocked:
        return Decision(status="blocked", hold_reason=None, reasons=blocked)
    if review:
        return Decision(status="held", hold_reason="review", reasons=review)
    if explicit_high and not verified:
        return Decision(status="blocked", hold_reason=None, reasons=["explicit"])
    return Decision(status="published", hold_reason=None, reasons=[])


def _score(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)
