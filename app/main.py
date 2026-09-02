import asyncio
import base64
import binascii
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models.generation import GenerateRequest, GenerationSettings, Style
from app.services.model_manager import ModelManager
from app.services.storage_service import StorageService
from app.services.tts_service import TTSService, VoiceService

LANGUAGE_HELP = "Target language: Auto, Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish, or Italian."
STYLE_HELP = "VoiceDesign only. Choose neutral, happy, cheerful, excited, calm, warm, sad, angry, frustrated, fearful, nervous, surprised, serious, dramatic, confident, gentle, or whispering."
LANGUAGES = ["Auto", "Chinese", "English", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]
EMOTIONS = ["neutral", "happy", "cheerful", "excited", "calm", "warm", "sad", "angry", "frustrated", "fearful", "nervous", "surprised", "serious", "dramatic", "confident", "gentle", "whispering"]
FORM_ENUMS = {"language": LANGUAGES, "emotion": EMOTIONS, "pace": ["slow", "medium", "medium_fast", "fast"], "energy": ["low", "medium", "high"], "pitch": ["low", "medium", "high"]}

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.models = ModelManager(settings)
    app.state.storage = StorageService(settings)
    app.state.voices = VoiceService(app.state.models, app.state.storage)
    app.state.tts = TTSService(app.state.models, app.state.storage, app.state.voices)
    app.state.gpu_slots = asyncio.Semaphore(settings.max_concurrent_generations)
    yield

app = FastAPI(title="Qwen3-TTS Service", version="2.0.0", description="Persistent named Qwen3-TTS voices. All POST/PATCH input is multipart form-data; synthesis requests wait and return a WAV file.", lifespan=lifespan)
app.mount("/app", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="app")

@app.middleware("http")
async def require_password(request: Request, call_next):
    password = get_settings().app_password
    if password is None or not password.get_secret_value():
        return JSONResponse(status_code=503, content={"detail": {"code": "password_not_configured", "message": "Set APP_PASSWORD in .env before starting the service."}})
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("basic "):
        try:
            _, supplied = base64.b64decode(authorization.split(" ", 1)[1]).decode("utf-8").split(":", 1)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            supplied = ""
        if secrets.compare_digest(supplied, password.get_secret_value()):
            return await call_next(request)
    return JSONResponse(status_code=401, content={"detail": {"code": "authentication_required", "message": "A valid application password is required."}}, headers={"WWW-Authenticate": 'Basic realm="Qwen Voice Studio", charset="UTF-8"'})

def custom_openapi():
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    for path in ("/voices/design", "/generate", "/generate/expressive"):
        content = schema["paths"][path]["post"]["requestBody"]["content"]
        form_schema = content.pop("application/x-www-form-urlencoded")
        content["multipart/form-data"] = form_schema
    storage = getattr(app.state, "storage", None)
    voice_names = sorted(voice["name"] for voice in storage.load_voices().values()) if storage else []
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            body = operation.get("requestBody", {}).get("content", {})
            for media_type in body.values():
                reference = media_type["schema"].get("$ref")
                if not reference:
                    continue
                properties = schema["components"]["schemas"][reference.rsplit("/", 1)[-1]]["properties"]
                for field, values in FORM_ENUMS.items():
                    if field in properties:
                        properties[field]["enum"] = values
                if "voice_name" in properties:
                    properties["voice_name"]["enum"] = voice_names
    return schema

app.openapi = custom_openapi

def style_from_form(emotion: str, intensity: float, pace: str | None, energy: str | None, pitch: str | None) -> Style:
    try:
        return Style(emotion=emotion, intensity=intensity, pace=pace, energy=energy, pitch=pitch)
    except Exception as exc:
        raise HTTPException(422, detail={"code": "invalid_style", "message": str(exc)})

def generation_from_form(do_sample: bool, top_k: int, top_p: float, temperature: float, repetition_penalty: float, max_new_tokens: int) -> GenerationSettings:
    try:
        return GenerationSettings(do_sample=do_sample, top_k=top_k, top_p=top_p, temperature=temperature, repetition_penalty=repetition_penalty, max_new_tokens=max_new_tokens)
    except Exception as exc:
        raise HTTPException(422, detail={"code": "invalid_generation_settings", "message": str(exc)})

def audio_response(path: Path, metadata: dict) -> FileResponse:
    return FileResponse(path, media_type="audio/wav", filename=f"{metadata['generation_id']}.wav", headers={"X-Generation-ID": metadata["generation_id"]})

@app.get("/health", tags=["health"], summary="Service and model status")
def health(request: Request):
    return {"status": "ok", **request.app.state.models.status()}

@app.get("/voices", tags=["voices"], summary="List saved voices")
def list_voices(request: Request, search: str | None = None):
    voices = list(request.app.state.storage.load_voices().values())
    if search: voices = [voice for voice in voices if search.casefold() in voice["name"].casefold()]
    return [request.app.state.voices.public(voice) for voice in voices]

@app.post("/voices", tags=["voices"], summary="Create a persistent cloned voice", description="Creates the official Base-model clone prompt once and reuses it for all future generation.")
async def create_voice(request: Request, name: str = Form(..., description="Human-readable unique voice name used in every later request."), reference_audio: UploadFile = File(..., description="Reference recording containing one clearly audible speaker."), reference_text: str | None = Form(None, description="Exact transcript of the reference recording. Required unless x_vector_only_mode is enabled."), language: str = Form("German", description=LANGUAGE_HELP), x_vector_only_mode: bool = Form(False, description="Use only speaker embedding; permits no transcript but can reduce clone quality."), description: str | None = Form(None, description="Optional note describing this saved voice.")):
    async with request.app.state.gpu_slots:
        voice = await request.app.state.voices.create_clone(name, reference_audio, reference_text, language, x_vector_only_mode, description)
    return request.app.state.voices.public(voice)

@app.get("/voices/{voice_name}", tags=["voices"], summary="Get a voice by name")
def get_voice(request: Request, voice_name: str):
    return request.app.state.voices.public(request.app.state.voices.get(voice_name))

@app.delete("/voices/{voice_name}", status_code=204, tags=["voices"], summary="Delete a voice by name")
def delete_voice(request: Request, voice_name: str, keep_reference: bool = False):
    request.app.state.voices.delete(voice_name, keep_reference)

@app.get("/voices/{voice_name}/audio", tags=["audio"], summary="List newest generated audio for a voice")
def list_voice_audio(request: Request, voice_name: str, limit: int = 5):
    voice = request.app.state.voices.get(voice_name)
    items = request.app.state.storage.list_audio_for_voice(voice["name"], min(max(limit, 1), 100))
    return [{**item, "audio_url": f"/audio/{item['generation_id']}"} for item in items]

@app.delete("/voices/{voice_name}/audio/{generation_id}", status_code=204, tags=["audio"], summary="Delete generated audio for a voice")
def delete_voice_audio(request: Request, voice_name: str, generation_id: str):
    voice = request.app.state.voices.get(voice_name)
    request.app.state.storage.delete_audio_for_voice(voice["name"], generation_id)

@app.delete("/voices/{voice_name}/audio", tags=["audio"], summary="Delete all generated audio for a voice")
def delete_all_voice_audio(request: Request, voice_name: str):
    voice = request.app.state.voices.get(voice_name)
    return {"deleted": request.app.state.storage.delete_all_audio_for_voice(voice["name"])}

@app.get("/voices/{voice_name}/reference-audio", tags=["voices"], response_class=FileResponse, summary="Play a voice reference recording")
def get_reference_audio(request: Request, voice_name: str):
    voice = request.app.state.voices.get(voice_name)
    path = Path(voice["reference_audio_path"])
    if not path.is_file():
        raise HTTPException(404, detail={"code": "reference_audio_not_found", "message": "Reference audio does not exist."})
    return FileResponse(path, media_type="audio/wav")

@app.get("/audio/{generation_id}", tags=["audio"], response_class=FileResponse, summary="Play a generated WAV")
def get_audio(request: Request, generation_id: str):
    path = request.app.state.storage.settings.generated_dir / f"{generation_id}.wav"
    if not path.is_file():
        raise HTTPException(404, detail={"code": "audio_not_found", "message": "Audio does not exist."})
    return FileResponse(path, media_type="audio/wav")

@app.post("/voices/design", tags=["voices"], summary="Design and save a reusable character voice", description="Generates a VoiceDesign reference clip, then creates one persistent Base clone prompt from it. Returns the named voice metadata after inference completes.")
async def design_voice(request: Request, name: str = Form(..., description="Unique human-readable name for the reusable character.", media_type="multipart/form-data"), reference_text: str = Form(..., description="Text used to create the character reference recording."), voice_description: str = Form(..., description="Natural-language persona and timbre description."), language: str = Form("German", description=LANGUAGE_HELP), emotion: str = Form("neutral", description=STYLE_HELP), intensity: float = Form(0.5, ge=0, le=1, description="Emotion strength from 0.0 subtle to 1.0 maximum."), pace: str | None = Form("medium", description="VoiceDesign only: slow, medium, medium_fast, or fast."), energy: str | None = Form("medium", description="VoiceDesign only: low, medium, or high."), pitch: str | None = Form("medium", description="VoiceDesign only: low, medium, or high."), do_sample: bool = Form(True, description="Official Transformers sampling switch."), top_k: int = Form(50, ge=1, description="Official top-k sampling value."), top_p: float = Form(1.0, gt=0, le=1, description="Official nucleus sampling value."), temperature: float = Form(0.9, gt=0, description="Official sampling temperature."), repetition_penalty: float = Form(1.05, gt=0, description="Official repetition penalty."), max_new_tokens: int = Form(2048, ge=1, le=4096, description="Maximum generated codec tokens.")):
    style = style_from_form(emotion, intensity, pace, energy, pitch)
    design_request = GenerateRequest(text=reference_text, language=language, mode="voice_design", voice_description=voice_description, style=style, generation=generation_from_form(do_sample, top_k, top_p, temperature, repetition_penalty, max_new_tokens))
    try:
        async with request.app.state.gpu_slots:
            audio_path, _ = await asyncio.to_thread(request.app.state.tts.generate, design_request)
            voice = await asyncio.to_thread(request.app.state.voices.create_from_reference, name, language, audio_path, reference_text, False, "designed_then_cloned", None, voice_description, style)
    except HTTPException: raise
    except Exception as exc: raise HTTPException(503, detail={"code": "design_generation_failed", "message": str(exc)})
    return request.app.state.voices.public(voice)

@app.post("/generate", tags=["generation"], response_class=FileResponse, summary="Generate WAV from a saved voice", description="Uses multipart form-data and holds the request open until generation is complete. The response body is the generated WAV.")
async def generate(request: Request, text: str = Form(..., description="Text to speak.", media_type="multipart/form-data"), voice_name: str = Form(..., description="Saved voice name from POST /voices."), language: str | None = Form("German", description="Override the voice default. " + LANGUAGE_HELP), do_sample: bool = Form(True, description="Official Transformers sampling switch."), top_k: int = Form(50, ge=1, description="Official top-k sampling value."), top_p: float = Form(1.0, gt=0, le=1, description="Official nucleus sampling value."), temperature: float = Form(0.9, gt=0, description="Official sampling temperature."), repetition_penalty: float = Form(1.05, gt=0, description="Official repetition penalty."), max_new_tokens: int = Form(2048, ge=1, le=4096, description="Maximum generated codec tokens.")):
    voice = request.app.state.voices.get(voice_name)
    payload = GenerateRequest(text=text, voice_name=voice_name, language=language, mode="faithful_clone", generation=generation_from_form(do_sample, top_k, top_p, temperature, repetition_penalty, max_new_tokens))
    async with request.app.state.gpu_slots:
        path, metadata = await asyncio.to_thread(request.app.state.tts.generate, payload, voice)
    return audio_response(path, metadata)

@app.post("/generate/expressive", tags=["generation"], response_class=FileResponse, summary="Generate expressive VoiceDesign WAV", description="Uses multipart form-data and returns a WAV after VoiceDesign generation completes. This does not use a saved cloned identity.")
async def expressive(request: Request, text: str = Form(..., description="Text to speak.", media_type="multipart/form-data"), voice_description: str = Form(..., description="Natural-language description of the desired voice."), language: str = Form("German", description=LANGUAGE_HELP), emotion: str = Form("neutral", description=STYLE_HELP), intensity: float = Form(0.5, ge=0, le=1, description="Emotion strength from 0.0 subtle to 1.0 maximum."), pace: str | None = Form("medium", description="slow, medium, medium_fast, or fast."), energy: str | None = Form("medium", description="low, medium, or high."), pitch: str | None = Form("medium", description="low, medium, or high."), do_sample: bool = Form(True, description="Official Transformers sampling switch."), top_k: int = Form(50, ge=1, description="Official top-k sampling value."), top_p: float = Form(1.0, gt=0, le=1, description="Official nucleus sampling value."), temperature: float = Form(0.9, gt=0, description="Official sampling temperature."), repetition_penalty: float = Form(1.05, gt=0, description="Official repetition penalty."), max_new_tokens: int = Form(2048, ge=1, le=4096, description="Maximum generated codec tokens.")):
    style = style_from_form(emotion, intensity, pace, energy, pitch)
    payload = GenerateRequest(text=text, language=language, mode="voice_design", voice_description=voice_description, style=style, generation=generation_from_form(do_sample, top_k, top_p, temperature, repetition_penalty, max_new_tokens))
    async with request.app.state.gpu_slots:
        path, metadata = await asyncio.to_thread(request.app.state.tts.generate, payload)
    return audio_response(path, metadata)
