from functools import lru_cache
from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    data_dir: Path = Path('/app/data')
    qwen_base_model: str = 'Qwen/Qwen3-TTS-12Hz-1.7B-Base'
    qwen_design_model: str = 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign'
    model_device: str = 'cuda:0'
    model_dtype: str = 'bfloat16'
    max_concurrent_generations: int = 1
    require_gpu: bool = True
    enable_flash_attention: bool = True
    app_password: SecretStr | None = None
    @property
    def voices_dir(self): return self.data_dir / 'voices'
    @property
    def references_dir(self): return self.data_dir / 'references'
    @property
    def generated_dir(self): return self.data_dir / 'generated'
@lru_cache
def get_settings(): return Settings()
