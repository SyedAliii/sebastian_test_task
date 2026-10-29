import math
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class MediaIn(BaseModel):
    type: Literal["image", "video"]
    source: Literal["upload", "generation"]
    prompt: str | None = None
    frames: list[dict[str, Any]] = Field(min_length=1)

    @field_validator("frames", mode="before")
    @classmethod
    def frames_are_score_objects(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        for frame in value:
            if not isinstance(frame, dict):
                raise ValueError("invalid_frame")
            for score in frame.values():
                if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
                    raise ValueError("score_out_of_range")
                if score < 0 or score > 1:
                    raise ValueError("score_out_of_range")
        return value

    @model_validator(mode="after")
    def check_shape(self) -> "MediaIn":
        reasons: list[str] = []
        if self.type == "image" and len(self.frames) != 1:
            reasons.append("image_must_have_one_frame")
        if self.source == "generation" and (self.prompt is None or self.prompt.strip() == ""):
            reasons.append("prompt_required")
        if self.source == "upload" and self.prompt is not None:
            reasons.append("upload_has_no_prompt")
        if reasons:
            raise ValueError(" ".join(reasons))
        return self


class MediaCreated(BaseModel):
    id: str
    status: str


class MediaOut(BaseModel):
    id: str
    status: str
    reasons: list
