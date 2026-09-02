import logging
from app.config import Settings
log=logging.getLogger(__name__)
class ModelManager:
 def __init__(self,settings:Settings): self.settings,self._models=settings,{}
 def _load(self,kind):
  if kind in self._models:return self._models[kind]
  import torch
  if self.settings.require_gpu and not torch.cuda.is_available():raise RuntimeError('GPU is required but CUDA is unavailable')
  from qwen_tts import Qwen3TTSModel
  kwargs={'device_map':self.settings.model_device,'dtype':getattr(torch,self.settings.model_dtype)}
  if self.settings.enable_flash_attention:kwargs['attn_implementation']='flash_attention_2'
  name=self.settings.qwen_base_model if kind=='base' else self.settings.qwen_design_model
  try:model=Qwen3TTSModel.from_pretrained(name,**kwargs)
  except Exception:
   if not self.settings.enable_flash_attention:raise
   log.warning('FlashAttention unavailable; retrying default attention');kwargs.pop('attn_implementation');model=Qwen3TTSModel.from_pretrained(name,**kwargs)
  self._models[kind]=model;return model
 def base(self):return self._load('base')
 def design(self):return self._load('design')
 def status(self):
  try:
   import torch;cuda=torch.cuda.is_available()
  except ImportError:cuda=False
  return {'base_model':{'loaded':'base'in self._models,'name':self.settings.qwen_base_model},'voice_design_model':{'loaded':'design'in self._models,'name':self.settings.qwen_design_model},'cuda':cuda}
