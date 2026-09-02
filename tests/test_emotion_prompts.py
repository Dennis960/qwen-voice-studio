from app.models.generation import Style
from app.services.emotion_prompts import build_instruction
def test_emotion_prompt_is_structured():
 prompt=build_instruction('Warm adult narrator',Style(emotion='angry',intensity=.8,pace='medium_fast',energy='high'))
 assert 'anger and determination' in prompt
 assert 'strong emotional intensity' in prompt
 assert 'medium-fast' in prompt
