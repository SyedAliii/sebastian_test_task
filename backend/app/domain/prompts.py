import re

_AGE = r"(?:1[0-7]|[1-9])"

_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "minor",
        (
            r"\bminor\b",
            r"\bunderage\b",
            r"\bchild\b",
            r"\bteen\b",
            r"\bschoolgirl\b",
            rf"\b{_AGE} year old\b",
            rf"\b{_AGE}yo\b",
        ),
    ),
    ("sexual_violence", (r"\brape\b", r"\bsexual violence\b", r"\bnon consensual\b")),
    ("bestiality", (r"\bbestiality\b",)),
    ("self_harm", (r"\bself harm\b", r"\bsuicide\b")),
    ("real_person", (r"\bcelebrity\b", r"\breal person\b")),
    ("incest", (r"\bincest\b",)),
    ("trafficking", (r"\btrafficking\b",)),
)


class PromptRefused(Exception):
    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons


def normalize_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.lower().replace("-", " ")).strip()


def prompt_refusal(prompt: str | None) -> list[str]:
    if prompt is None or prompt.strip() == "":
        return []
    text = normalize_prompt(prompt)
    return [category for category, patterns in _RULES if any(re.search(pattern, text) for pattern in patterns)]
