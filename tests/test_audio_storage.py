import json
from pathlib import Path

from app.services.storage_service import StorageService


class Settings:
    def __init__(self, root: Path):
        self.data_dir = root
        self.voices_dir = root / "voices"
        self.references_dir = root / "references"
        self.generated_dir = root / "generated"


def test_lists_and_deletes_only_the_selected_voice_audio(tmp_path):
    storage = StorageService(Settings(tmp_path))
    first = {"generation_id": "first", "voice_name": "Narrator", "text": "Hello"}
    other = {"generation_id": "other", "voice_name": "Other", "text": "No"}
    for metadata in (first, other):
        (storage.settings.generated_dir / f"{metadata['generation_id']}.wav").touch()
        (storage.settings.generated_dir / f"{metadata['generation_id']}.json").write_text(json.dumps(metadata))

    assert [item["generation_id"] for item in storage.list_audio_for_voice("narrator")] == ["first"]
    storage.delete_audio_for_voice("Narrator", "first")
    assert storage.list_audio_for_voice("Narrator") == []
    assert (storage.settings.generated_dir / "other.wav").is_file()
