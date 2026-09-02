import json
import shutil
from pathlib import Path

import soundfile as sf
from fastapi import HTTPException, UploadFile


class StorageService:
    def __init__(self, settings):
        self.settings = settings
        for directory in (settings.data_dir, settings.voices_dir, settings.references_dir, settings.generated_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.registry_path = settings.voices_dir / "registry.json"
        if not self.registry_path.exists():
            self.registry_path.write_text("{}")

    def load_voices(self) -> dict[str, dict]:
        try:
            return json.loads(self.registry_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(500, detail={"code": "voice_registry_error", "message": str(exc)})

    def save_voices(self, voices: dict[str, dict]) -> None:
        temporary = self.registry_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(voices, indent=2, sort_keys=True))
        temporary.replace(self.registry_path)

    async def save_reference(self, key: str, upload: UploadFile) -> Path:
        suffix = Path(upload.filename or "reference.wav").suffix.lower() or ".wav"
        path = self.settings.references_dir / f"{key}{suffix}"
        with path.open("wb") as target:
            shutil.copyfileobj(upload.file, target)
        self.validate_audio(path)
        return path

    def validate_audio(self, path: Path) -> None:
        try:
            info = sf.info(path)
            if info.frames <= 0 or info.samplerate <= 0:
                raise ValueError("audio contains no frames")
        except Exception as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(422, detail={"code": "invalid_audio", "message": str(exc)})

    def prompt_path(self, key: str) -> Path:
        return self.settings.voices_dir / f"{key}.pt"

    def save_audio(self, generation_id: str, waveform, sample_rate: int, metadata: dict) -> Path:
        path = self.settings.generated_dir / f"{generation_id}.wav"
        sf.write(path, waveform, sample_rate)
        path.with_suffix(".json").write_text(json.dumps(metadata, default=str, indent=2))
        return path

    def list_audio_for_voice(self, voice_name: str) -> list[dict]:
        items = []
        for metadata_path in self.settings.generated_dir.glob("*.json"):
            try:
                metadata = json.loads(metadata_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if str(metadata.get("voice_name") or "").casefold() == voice_name.casefold():
                generation_id = metadata.get("generation_id")
                if generation_id and (self.settings.generated_dir / f"{generation_id}.wav").is_file():
                    items.append(metadata)
        return sorted(items, key=lambda item: item.get("generation_id", ""), reverse=True)

    def delete_audio_for_voice(self, voice_name: str, generation_id: str) -> None:
        metadata_path = self.settings.generated_dir / f"{generation_id}.json"
        if not metadata_path.is_file():
            raise HTTPException(404, detail={"code": "audio_not_found", "message": "Audio does not exist."})
        try:
            metadata = json.loads(metadata_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(409, detail={"code": "invalid_audio_metadata", "message": str(exc)})
        if str(metadata.get("voice_name") or "").casefold() != voice_name.casefold():
            raise HTTPException(404, detail={"code": "audio_not_found", "message": "Audio does not belong to this voice."})
        (self.settings.generated_dir / f"{generation_id}.wav").unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
