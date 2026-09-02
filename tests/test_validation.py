import pytest
from pydantic import ValidationError
from app.models.generation import GenerateRequest,Style
def test_design_requires_description():
 with pytest.raises(ValidationError):GenerateRequest(text='test',mode='voice_design')
def test_intensity_is_bounded():
 with pytest.raises(ValidationError):Style(intensity=1.1)
