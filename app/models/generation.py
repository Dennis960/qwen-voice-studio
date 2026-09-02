from typing import Literal

from pydantic import BaseModel, Field, model_validator

Emotion = Literal['neutral', 'happy', 'cheerful', 'excited', 'calm', 'warm', 'sad', 'angry', 'frustrated', 'fearful', 'nervous', 'surprised', 'serious', 'dramatic', 'confident', 'gentle', 'whispering']


class Style(BaseModel):
    emotion: Emotion = 'neutral'
    intensity: float = Field(.5, ge=0, le=1)
    pace: Literal['slow', 'medium', 'medium_fast', 'fast'] | None = None
    energy: Literal['low', 'medium', 'high'] | None = None
    pitch: Literal['low', 'medium', 'high'] | None = None


class GenerationSettings(BaseModel):
    do_sample: bool = True
    top_k: int = Field(50, ge=1)
    top_p: float = Field(1, gt=0, le=1)
    temperature: float = Field(.9, gt=0)
    repetition_penalty: float = Field(1.05, gt=0)
    max_new_tokens: int = Field(2048, ge=1, le=4096)


class GenerateRequest(BaseModel):
    text: str = Field(min_length=1)
    voice_name: str | None = None
    language: str | None = None
    mode: Literal['faithful_clone', 'voice_design'] = 'faithful_clone'
    voice_description: str | None = None
    style: Style | None = None
    generation: GenerationSettings = Field(default_factory=GenerationSettings)

    @model_validator(mode='after')
    def validate_mode(self):
        if self.mode == 'faithful_clone' and not self.voice_name:
            raise ValueError('voice_name is required for faithful_clone')
        if self.mode == 'voice_design' and not self.voice_description:
            raise ValueError('voice_description is required for voice_design')
        return self
