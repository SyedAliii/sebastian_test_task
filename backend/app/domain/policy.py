def frames_for_provider(frames: list, mode: str) -> list:
    if mode == "broken":
        return frames[:8]
    return list(frames)


def timeout_publishes(mode: str) -> bool:
    return mode == "broken"


def prompt_refusal(prompt: str | None) -> list[str]:
    from app.domain.prompts import prompt_refusal as match_prompt

    return match_prompt(prompt)
