import math

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ControlRequest(BaseModel):
    mode: Literal["ok", "slow", "timeout", "error"]
    delay_ms: int = Field(default=0, ge=0)
    error_kind: Literal["http_500", "http_429", "malformed"] = "http_500"

    @field_validator("delay_ms", mode="before")
    @classmethod
    def delay_ms_must_be_int(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("delay_ms must be an integer")
        return value


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    media_id: str = Field(min_length=1)
    frames: list[dict[str, float]] = Field(min_length=1)

    @field_validator("frames", mode="before")
    @classmethod
    def frames_must_be_scores(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        for frame in value:
            if not isinstance(frame, dict):
                raise ValueError("each frame must be an object")
            for score in frame.values():
                if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
                    raise ValueError("score must be a number from 0 to 1")
                if score < 0 or score > 1:
                    raise ValueError("score must be a number from 0 to 1")
        return value
