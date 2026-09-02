# Qwen3-TTS Service

A self-hosted NVIDIA GPU service for persistent, named Qwen3-TTS voices. Open the Voice Studio at `http://localhost:8000/app/` to create, manage, test, and listen to voices in the browser. Swagger is available at `http://localhost:8000/docs` for field-level descriptions, permitted values, and an interactive multipart form.

## Start

Install Docker Engine, Docker Compose v2, an NVIDIA driver, and NVIDIA Container Toolkit. Confirm GPU Docker access with:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

Set `APP_PASSWORD` in `.env` to a long unique value. Set `HF_TOKEN` only if Hugging Face requires authentication, then run:

```bash
docker compose up -d --build
```

The service downloads models lazily on the first relevant request. Persistent voices, audio, and model cache are under `./data`.

## API

Every HTTP request, including `/app/`, `/docs`, and `/openapi.json`, requires HTTP Basic Auth. Use any username and `APP_PASSWORD` as its password. The Compose port is bound to `127.0.0.1` by default, so it is not exposed to the local network. For remote access, place the service behind a TLS-terminating reverse proxy; do not expose HTTP Basic Auth over plain HTTP. Every API that accepts input (`POST` and `PATCH`) uses `multipart/form-data`. Every synthesis request waits for the GPU result and returns `audio/wav` directly. It also stores a WAV and JSON metadata file under `data/generated`.

Voice names are the stable identifiers. Names accept letters, digits, spaces, `_`, and `-`, are matched case-insensitively, and must be unique. Use URL encoding for names containing spaces in path endpoints.

Create a German clone:

```bash
curl -u user:"$APP_PASSWORD" -X POST http://localhost:8000/voices \
  -F 'name=Meine Stimme' \
  -F 'reference_audio=@reference.wav' \
  -F 'reference_text=Guten Tag, dies ist meine Referenzaufnahme.' \
  -F 'language=German'
```

Generate and write the direct WAV response:

```bash
curl -u user:"$APP_PASSWORD" -X POST http://localhost:8000/generate \
  -F 'text=Guten Morgen, willkommen im System.' \
  -F 'voice_name=Meine Stimme' \
  --output output.wav
```

Generate expressive speech with VoiceDesign:

```bash
curl -u user:"$APP_PASSWORD" -X POST http://localhost:8000/generate/expressive \
  -F 'text=Das ist wirklich unglaublich!' \
  -F 'voice_description=Young energetic female voice' \
  -F 'language=German' \
  -F 'emotion=excited' -F 'intensity=0.9' -F 'energy=high' \
  --output expressive.wav
```

Manage voices with `GET /voices`, `GET /voices/{voice_name}`, `PATCH /voices/{voice_name}`, and `DELETE /voices/{voice_name}`. The patch form supports `description`, comma-separated `tags`, and the default `language`.

## Modes

- Saved voices use the Base model and the exact persistent output of `create_voice_clone_prompt`, which maximizes identity consistency.
- `/generate/expressive` uses VoiceDesign's official `generate_voice_design(text, language, instruct)` API. Style form fields are translated into its natural-language instruction.
- `/voices/design` generates a VoiceDesign reference, then builds and saves a reusable Base clone prompt.

The Base clone API does not accept arbitrary emotion instructions for an existing clone. For it, emotion follows the reference recording, text semantics, and model behavior. Use VoiceDesign when dynamic emotion and style control matter.
