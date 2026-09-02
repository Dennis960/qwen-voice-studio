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
    first = {"generation_id": "first", "created_at": "2026-01-01T00:00:00+00:00", "voice_name": "Narrator", "text": "Hello"}
    newest = {"generation_id": "newest", "created_at": "2026-02-01T00:00:00+00:00", "voice_name": "Narrator", "text": "New"}
    other = {"generation_id": "other", "voice_name": "Other", "text": "No"}
    for metadata in (first, newest, other):
        (storage.settings.generated_dir / f"{metadata['generation_id']}.wav").touch()
        (storage.settings.generated_dir / f"{metadata['generation_id']}.json").write_text(json.dumps(metadata))

    assert [item["generation_id"] for item in storage.list_audio_for_voice("narrator", limit=1)] == ["newest"]
    storage.delete_audio_for_voice("Narrator", "first")
    assert [item["generation_id"] for item in storage.list_audio_for_voice("Narrator", limit=5)] == ["newest"]
    assert storage.delete_all_audio_for_voice("Narrator") == 1
    assert storage.list_audio_for_voice("Narrator", limit=5) == []
    assert (storage.settings.generated_dir / "other.wav").is_file()
