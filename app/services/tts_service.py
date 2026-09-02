import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import torch
from fastapi import HTTPException, UploadFile

from app.models.generation import GenerateRequest, Style
from app.services.emotion_prompts import build_instruction


class VoiceService:
    def __init__(self, models, storage):
        self.models = models
        self.storage = storage

    def key_for(self, name: str) -> str:
        normalized = name.strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,63}", normalized):
            raise HTTPException(422, detail={"code": "invalid_voice_name", "message": "Use 1-64 letters, digits, spaces, underscores, or hyphens."})
        return normalized.casefold()

    def public(self, voice: dict) -> dict:
        return {
            "name": voice["name"],
            "type": voice["type"],
            "language": voice["language"],
            "reference_text": voice.get("reference_text"),
            "voice_description": voice.get("voice_description"),
            "x_vector_only_mode": voice.get("x_vector_only_mode", False),
            "reference_audio_url": f"/voices/{voice['name']}/reference-audio",
            "prompt": {
                "format": 1,
                "base_model": self.models.settings.qwen_base_model,
                "mode": "x-vector only" if voice.get("x_vector_only_mode") else "ICL clone prompt",
                "stored": bool(voice.get("voice_prompt_path")),
            },
            "created_at": voice.get("created_at"),
        }

    def get(self, name: str) -> dict:
        voice = self.storage.load_voices().get(self.key_for(name))
        if not voice:
            raise HTTPException(404, detail={"code": "voice_not_found", "message": f"Voice '{name}' does not exist."})
        return voice

    def save_prompt(self, key: str, prompt: object) -> Path:
        path = self.storage.prompt_path(key)
        torch.save({"format": 1, "base_model": self.models.settings.qwen_base_model, "prompt": prompt}, path)
        return path

    def prompt(self, voice: dict) -> object:
        try:
            payload = torch.load(voice["voice_prompt_path"], map_location=self.models.settings.model_device, weights_only=False)
        except Exception as exc:
            raise HTTPException(409, detail={"code": "invalid_voice_prompt", "message": str(exc)})
        if payload.get("format") != 1 or payload.get("base_model") != self.models.settings.qwen_base_model:
            raise HTTPException(409, detail={"code": "incompatible_voice_prompt", "message": "Voice was created with a different Base model."})
        return payload["prompt"]

    def create_from_reference(self, name: str, language: str, reference_path: Path, reference_text: str | None, x_vector_only_mode: bool, voice_type: str, description: str | None = None, voice_description: str | None = None, style: Style | None = None) -> dict:
        key = self.key_for(name)
        voices = self.storage.load_voices()
        if key in voices:
            raise HTTPException(409, detail={"code": "voice_already_exists", "message": "Voice names must be unique, ignoring case."})
        if not x_vector_only_mode and not reference_text:
            raise HTTPException(422, detail={"code": "missing_reference_transcript", "message": "reference_text is required unless x_vector_only_mode is enabled."})
        try:
            prompt = self.models.base().create_voice_clone_prompt(ref_audio=str(reference_path), ref_text=reference_text, x_vector_only_mode=x_vector_only_mode)
        except Exception as exc:
            raise HTTPException(422, detail={"code": "voice_prompt_creation_failed", "message": str(exc)})
        voice = {"name": name.strip(), "type": voice_type, "language": language, "description": description, "tags": [], "reference_text": reference_text, "x_vector_only_mode": x_vector_only_mode, "voice_description": voice_description, "default_style": style.model_dump() if style else None, "reference_audio_path": str(reference_path), "voice_prompt_path": str(self.save_prompt(key, prompt)), "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
        voices[key] = voice
        self.storage.save_voices(voices)
        return voice

    async def create_clone(self, name: str, upload: UploadFile, reference_text: str | None, language: str, x_vector_only_mode: bool, description: str | None) -> dict:
        key = self.key_for(name)
        if key in self.storage.load_voices():
            raise HTTPException(409, detail={"code": "voice_already_exists", "message": "Voice names must be unique, ignoring case."})
        reference = await self.storage.save_reference(key, upload)
        try:
            return self.create_from_reference(name, language, reference, reference_text, x_vector_only_mode, "clone", description)
        except Exception:
            reference.unlink(missing_ok=True)
            raise

    def update(self, name: str, description: str | None, tags: str | None, language: str | None) -> dict:
        key = self.key_for(name)
        voices = self.storage.load_voices()
        voice = voices.get(key)
        if not voice:
            raise HTTPException(404, detail={"code": "voice_not_found", "message": f"Voice '{name}' does not exist."})
        if description is not None: voice["description"] = description
        if tags is not None: voice["tags"] = [tag.strip() for tag in tags.split(",") if tag.strip()]
        if language is not None: voice["language"] = language
        voice["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.storage.save_voices(voices)
        return voice

    def delete(self, name: str, keep_reference: bool) -> None:
        key = self.key_for(name)
        voices = self.storage.load_voices()
        voice = voices.pop(key, None)
        if not voice:
            raise HTTPException(404, detail={"code": "voice_not_found", "message": f"Voice '{name}' does not exist."})
        Path(voice["voice_prompt_path"]).unlink(missing_ok=True)
        if not keep_reference: Path(voice["reference_audio_path"]).unlink(missing_ok=True)
        self.storage.save_voices(voices)


class TTSService:
    def __init__(self, models, storage, voices):
        self.models, self.storage, self.voices = models, storage, voices

    def generate(self, request: GenerateRequest, voice: dict | None = None) -> tuple[Path, dict]:
        generation_id = str(uuid.uuid4())
        kwargs = request.generation.model_dump()
        instruction = None
        if request.mode == "faithful_clone":
            if not voice: raise HTTPException(422, detail={"code": "missing_voice_name", "message": "voice_name is required for faithful_clone."})
            wavs, sample_rate = self.models.base().generate_voice_clone(text=request.text, language=request.language or voice["language"], voice_clone_prompt=self.voices.prompt(voice), **kwargs)
        else:
            instruction = build_instruction(request.voice_description or "", request.style)
            wavs, sample_rate = self.models.design().generate_voice_design(text=request.text, language=request.language or "Auto", instruct=instruction, **kwargs)
        metadata = {"generation_id": generation_id, "created_at": datetime.now(timezone.utc).isoformat(), "voice_name": voice["name"] if voice else None, "mode": request.mode, "text": request.text, "language": request.language, "generation": kwargs, "style": request.style.model_dump() if request.style else None, "resolved_instruction": instruction}
        return self.storage.save_audio(generation_id, wavs[0], sample_rate, metadata), metadata
