import os
import base64

os.environ['APP_PASSWORD'] = 'test-only-password'

from fastapi.testclient import TestClient
from app.config import get_settings
get_settings.cache_clear()
from app.main import app
from app.services.tts_service import VoiceService


def client():
    credentials = base64.b64encode(b'test:test-only-password').decode('ascii')
    return TestClient(app, headers={'Authorization': f'Basic {credentials}'})


def test_voice_names_are_case_insensitive_and_safe():
    service = VoiceService(None, None)
    assert service.key_for('Meine Stimme') == 'meine stimme'


def test_voice_name_rejects_path_like_values():
    service = VoiceService(None, None)
    try:
        service.key_for('../voice')
    except Exception as error:
        assert error.status_code == 422
    else:
        raise AssertionError('unsafe voice name was accepted')


def test_generate_is_documented_as_multipart():
    schema = client().get('/openapi.json').json()
    content = schema['paths']['/generate']['post']['requestBody']['content']
    assert 'multipart/form-data' in content
    body = content['multipart/form-data']['schema']['$ref'].split('/')[-1]
    properties = schema['components']['schemas'][body]['properties']
    assert 'German' in properties['language']['enum']
    assert properties['language']['default'] == 'German'
    assert properties['voice_name']['enum'] == []


def test_voice_studio_is_served():
    response = client().get('/app/')
    assert response.status_code == 200
    assert 'Qwen Voice Studio' in response.text


def test_api_rejects_requests_without_password():
    response = TestClient(app).get('/health')
    assert response.status_code == 401
    assert response.headers['www-authenticate'].startswith('Basic')
