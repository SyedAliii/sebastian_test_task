from app.domain.labels import LABELS


def normalize_frames(frames: list[dict[str, float]]) -> list[dict[str, float]]:
    return [{label: frame.get(label, 0.0) for label in LABELS} for frame in frames]
