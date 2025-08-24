import os
import tempfile
import io
import uvicorn
from fastapi import FastAPI, HTTPException, Response, Request
from pydantic import BaseModel
from gtts import gTTS

app = FastAPI(title="GTTS OpenAI Compatible API", version="1.0.0")

# Load API keys from environment
GTTS_AUTH_KEYS = os.getenv("GTTS_AUTH_KEYS", "").split(",") if os.getenv("GTTS_AUTH_KEYS") else []
GTTS_AUTH_KEYS = [key.strip() for key in GTTS_AUTH_KEYS if key.strip()]  # Clean up whitespace and empty keys

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Skip auth for health check and root endpoints
    if request.url.path in ["/health", "/", "/docs", "/openapi.json"]:
        response = await call_next(request)
        return response

    # If no API keys configured, skip auth
    if not GTTS_AUTH_KEYS:
        response = await call_next(request)
        return response

    # Check authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Use: Authorization: Bearer <your-api-key>"
        )

    api_key = auth_header.split("Bearer ")[1].strip()
    if api_key not in GTTS_AUTH_KEYS:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    response = await call_next(request)
    return response

class TTSRequest(BaseModel):
    model: str = "tts-1"
    input: str
    voice: str = "alloy"
    response_format: str = "mp3"
    speed: float = 1.0

    # Main language fields
    language: str = None  # Our main parameter
    lang: str = None      # Short version

    # Alternative fields where language might be passed
    locale: str = None           # locale format (en_US, ru_RU)
    language_code: str = None    # explicit language code specification
    target_language: str = None  # target language
    speech_language: str = None  # speech language
    tts_language: str = None     # TTS specific

    # Fields from popular libraries/APIs
    source_language: str = None  # Google Translate style
    from_language: str = None    # some translators
    audio_language: str = None   # audio-specific
    output_language: str = None  # output language

    # Regional variants
    region: str = None           # region (us, gb, au)
    country: str = None          # country

    # Additional parameters (optional, non-standard)
    accent: str = None           # accent
    dialect: str = None          # dialect

def extract_language_from_request(request: TTSRequest) -> str:
    """Extracts language from various possible request fields"""

    # List of fields to check in priority order
    language_fields = [
        request.language,
        request.lang,
        request.language_code,
        request.speech_language,
        request.tts_language,
        request.target_language,
        request.source_language,
        request.audio_language,
        request.output_language,
        request.from_language
    ]

    # Check each field
    for lang_value in language_fields:
        if lang_value:
            # Normalize language (remove regions, convert to lowercase)
            normalized = normalize_language_code(lang_value.lower())
            if normalized in SUPPORTED_LANGUAGES:
                return normalized

    # Check locale format (en_US -> en)
    if request.locale:
        locale_lang = request.locale.lower().split('_')[0].split('-')[0]
        if locale_lang in SUPPORTED_LANGUAGES:
            return locale_lang

    # Fallback to voice mapping
    return VOICE_MAPPING.get(request.voice, "en")

def normalize_language_code(lang_code: str) -> str:
    """Normalizes language code to standard format"""
    # Remove regions: en-US -> en, zh-CN -> zh-cn
    if '-' in lang_code:
        parts = lang_code.split('-')
        base_lang = parts[0]

        # Special cases for regional variants
        regional_mappings = {
            'en-us': 'en-us',
            'en-gb': 'en-gb',
            'en-au': 'en-au',
            'pt-br': 'pt-br',
            'zh-cn': 'zh-cn',
            'zh-tw': 'zh-tw'
        }

        full_code = f"{base_lang}-{parts[1]}"
        if full_code in regional_mappings:
            return regional_mappings[full_code]
        else:
            return base_lang

    # Remove regions via underscore: en_US -> en
    if '_' in lang_code:
        return lang_code.split('_')[0]

    return lang_code

# Supported languages (extended list)
SUPPORTED_LANGUAGES = {
    # Main European languages
    "en": "English",
    "ru": "Russian",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "cs": "Czech",
    "sk": "Slovak",

    # Baltic languages
    "lv": "Latvian",
    "lt": "Lithuanian",
    "et": "Estonian",

    # Slavic languages
    "uk": "Ukrainian",
    "bg": "Bulgarian",
    "hr": "Croatian",
    "sr": "Serbian",
    "sl": "Slovenian",

    # Scandinavian languages
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",

    # Asian languages
    "zh": "Chinese (Mandarin)",
    "ja": "Japanese",
    "ko": "Korean",
    "hi": "Hindi",
    "th": "Thai",
    "vi": "Vietnamese",

    # Other popular languages
    "ar": "Arabic",
    "tr": "Turkish",
    "he": "Hebrew",
    "el": "Greek",
    "hu": "Hungarian",
    "ro": "Romanian",

    # Regional variants
    "en-us": "English (US)",
    "en-gb": "English (UK)",
    "en-au": "English (Australia)",
    "pt-br": "Portuguese (Brazil)",
    "zh-cn": "Chinese (Simplified)",
    "zh-tw": "Chinese (Traditional)"
}

# Mapping OpenAI voices to language codes (fallback if language not specified)
VOICE_MAPPING = {
    "alloy": "en",
    "echo": "ru",
    "fable": "lv",
    "onyx": "uk",
    "nova": "fr",
    "shimmer": "de"
}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/")
async def root():
    return {
        "message": "GTTS OpenAI Compatible API",
        "version": "1.0.0",
        "supported_languages": SUPPORTED_LANGUAGES
    }

@app.get("/v1/audio/languages")
async def get_supported_languages():
    """Get list of all supported languages"""
    return {
        "languages": SUPPORTED_LANGUAGES,
        "total_count": len(SUPPORTED_LANGUAGES),
        "usage": "Use language code in 'language' parameter when calling /v1/audio/speech"
    }

@app.post("/v1/audio/speech")
async def create_speech(request: TTSRequest):
    try:
        # Extract language from any possible field
        lang = extract_language_from_request(request)

        # Warnings about unsupported parameters
        warnings = []
        if request.voice and request.voice != "alloy":
            warnings.append(f"Voice '{request.voice}' not supported by gTTS, using default voice")

        if request.response_format and request.response_format != "mp3":
            warnings.append(f"Format '{request.response_format}' not supported by gTTS, using MP3")

        # Create TTS object with supported parameters
        tts = gTTS(
            text=request.input,
            lang=lang,
            slow=request.speed < 1.0  # only "voice" parameter we can control
        )

        # Save to memory buffer
        audio_buffer = io.BytesIO()
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)

        # Form response headers
        headers = {
            "Content-Disposition": "attachment; filename=speech.mp3",
            "X-Used-Language": lang,  # Return which language was used
            "X-Actual-Format": "mp3",  # Actual format
            "X-Actual-Voice": f"gTTS-{lang}",  # Actual voice
        }

        # Add warnings to headers if any
        if warnings:
            headers["X-Warnings"] = "; ".join(warnings)

        return Response(
            content=audio_buffer.read(),
            media_type="audio/mpeg",
            headers=headers
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS Error: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("OPENAI_API_HOST", "0.0.0.0"),
        port=int(os.getenv("OPENAI_API_PORT", "5002"))
    )
