from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv
from google import genai
from google.genai import types

import requests
import os
import re
import time

from urllib.parse import urlparse, parse_qs


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
YOUTUBETRANSCRIPT_API_KEY = os.getenv("YOUTUBETRANSCRIPT_API_KEY")


# ============================================================
# FLASK SETUP
# ============================================================

app = Flask(__name__)

CORS(app)


# ============================================================
# CONSTANTS
# ============================================================

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# OpenRouter fallback model
AI_MODEL = "openrouter/free"

# Faster provider selection
AI_PROVIDER_SORT = "throughput"

# Gemini primary model
GEMINI_MODEL = "gemini-3.5-flash-lite"

# Timeouts
AI_TIMEOUT = 60

# OpenRouter retries
AI_MAX_RETRIES = 2


# ============================================================
# GEMINI CLIENT
# ============================================================

gemini_client = None

if GEMINI_API_KEY:

    try:

        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        print("Gemini client initialized.")

    except Exception as error:

        print(
            "Gemini client initialization error:",
            error
        )

else:

    print(
        "WARNING: GEMINI_API_KEY is missing from .env"
    )


# ============================================================
# EXTRACT YOUTUBE VIDEO ID
# ============================================================

def extract_video_id(url):

    if not isinstance(url, str):
        return None

    url = url.strip()

    if not url:
        return None

    if not re.match(
        r"^https?://",
        url,
        re.IGNORECASE
    ):
        url = "https://" + url

    try:

        parsed = urlparse(url)

        hostname = (
            parsed.hostname or ""
        ).lower()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        # ----------------------------------------------------
        # youtube.com
        # ----------------------------------------------------

        if hostname in [
            "youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtube-nocookie.com",
        ]:

            path = parsed.path.rstrip("/")

            # Normal video
            if path == "/watch":

                query = parse_qs(
                    parsed.query
                )

                video_id = query.get(
                    "v",
                    [None]
                )[0]

                if video_id and re.fullmatch(
                    r"[A-Za-z0-9_-]{11}",
                    video_id
                ):
                    return video_id

            # Shorts / Live / Embed
            for prefix in [
                "/shorts/",
                "/live/",
                "/embed/"
            ]:

                if path.startswith(prefix):

                    video_id = (
                        path[len(prefix):]
                        .split("/")[0]
                    )

                    if re.fullmatch(
                        r"[A-Za-z0-9_-]{11}",
                        video_id
                    ):
                        return video_id

        # ----------------------------------------------------
        # youtu.be
        # ----------------------------------------------------

        elif hostname == "youtu.be":

            video_id = (
                parsed.path
                .strip("/")
                .split("/")[0]
            )

            if re.fullmatch(
                r"[A-Za-z0-9_-]{11}",
                video_id
            ):
                return video_id

    except Exception as error:

        print(
            "URL parsing error:",
            error
        )

    return None


# ============================================================
# CLEAN AI RESPONSE
# ============================================================

def clean_ai_response(answer):

    if not isinstance(answer, str):
        return ""

    answer = answer.strip()

    unwanted_patterns = [

        r"^\s*User\s*Safety\s*:\s*safe\s*$",

        r"^\s*User\s*Safety\s*:\s*unsafe\s*$",

        r"^\s*Safety\s*:\s*safe\s*$",

        r"^\s*Safety\s*:\s*unsafe\s*$",

        r"^\s*Safety\s*check\s*:\s*safe\s*$",

        r"^\s*Safety\s*check\s*:\s*unsafe\s*$",

    ]

    lines = answer.splitlines()

    cleaned_lines = []

    for line in lines:

        should_remove = False

        for pattern in unwanted_patterns:

            if re.match(
                pattern,
                line,
                re.IGNORECASE
            ):

                should_remove = True

                break

        if not should_remove:

            cleaned_lines.append(line)

    answer = "\n".join(
        cleaned_lines
    ).strip()

    # Remove accidental assistant/model prefix

    answer = re.sub(
        r"^\s*(assistant|model)\s*:\s*",
        "",
        answer,
        flags=re.IGNORECASE
    )

    return answer.strip()


# ============================================================
# GEMINI AI FUNCTION
# ============================================================

def call_gemini(
    system_prompt,
    user_prompt,
    max_tokens=1000
):

    if not gemini_client:

        return {

            "success": False,

            "error":
                "GEMINI_API_KEY is missing from .env"
        }

    try:

        print(
            "Gemini request started..."
        )

        combined_prompt = f"""
SYSTEM INSTRUCTIONS:

{system_prompt}

---

USER REQUEST:

{user_prompt}
"""

        response = (
            gemini_client
            .models
            .generate_content(

                model=GEMINI_MODEL,

                contents=combined_prompt,

                config=types.GenerateContentConfig(

                    temperature=0.2,

                    max_output_tokens=max_tokens
                )
            )
        )

        answer = ""

        try:

            answer = response.text or ""

        except Exception:

            answer = ""

        answer = clean_ai_response(
            answer
        )

        if not answer:

            print(
                "Gemini returned empty response."
            )

            return {

                "success": False,

                "error":
                    "Gemini returned an empty response."
            }

        print(
            "Gemini response received successfully."
        )

        return {

            "success": True,

            "answer": answer
        }

    except Exception as error:

        error_text = str(error)

        print(
            "Gemini error:",
            error_text
        )

        return {

            "success": False,

            "error":
                "Gemini request failed.",

            "details":
                error_text
        }


# ============================================================
# OPENROUTER AI FUNCTION
# ============================================================

def call_openrouter(
    system_prompt,
    user_prompt,
    max_tokens=1000
):

    if not OPENROUTER_API_KEY:

        return {

            "success": False,

            "error":
                "OPENROUTER_API_KEY is missing from .env"
        }

    headers = {

        "Authorization":
            f"Bearer {OPENROUTER_API_KEY}",

        "Content-Type":
            "application/json",

        "HTTP-Referer":
            "http://localhost:5000",

        "X-Title":
            "Vidora AI"
    }

    payload = {

        "model":
            AI_MODEL,

        "messages": [

            {

                "role":
                    "system",

                "content":
                    system_prompt
            },

            {

                "role":
                    "user",

                "content":
                    user_prompt
            }

        ],

        "temperature":
            0.2,

        "max_tokens":
            max_tokens,

        "provider": {

            "sort":
                AI_PROVIDER_SORT
        }
    }

    last_error = None

    retryable_statuses = [

        408,
        409,
        429,
        500,
        502,
        503,
        504
    ]

    for attempt in range(
        1,
        AI_MAX_RETRIES + 1
    ):

        try:

            print(
                f"OpenRouter request attempt "
                f"{attempt}/{AI_MAX_RETRIES}"
            )

            response = requests.post(

                OPENROUTER_URL,

                headers=headers,

                json=payload,

                timeout=AI_TIMEOUT
            )

            try:

                result = response.json()

            except ValueError:

                result = {}

            # ------------------------------------------------
            # SUCCESS
            # ------------------------------------------------

            if response.status_code == 200:

                choices = result.get(
                    "choices",
                    []
                )

                answer = ""

                if choices:

                    answer = (
                        choices[0]
                        .get("message", {})
                        .get("content", "")
                    )

                answer = clean_ai_response(
                    answer
                )

                if answer:

                    print(
                        "OpenRouter response "
                        "received successfully."
                    )

                    return {

                        "success":
                            True,

                        "answer":
                            answer
                    }

                last_error = (
                    "OpenRouter returned "
                    "an empty response."
                )

            # ------------------------------------------------
            # ERROR
            # ------------------------------------------------

            else:

                error_data = result.get(
                    "error",
                    {}
                )

                if isinstance(
                    error_data,
                    dict
                ):

                    last_error = (
                        error_data.get(
                            "message"
                        )
                        or
                        str(error_data)
                    )

                else:

                    last_error = str(
                        error_data
                        or
                        f"HTTP {response.status_code}"
                    )

                print(
                    "OpenRouter error:",
                    response.status_code,
                    last_error
                )

                if (
                    response.status_code
                    not in retryable_statuses
                ):

                    return {

                        "success":
                            False,

                        "error":
                            "OpenRouter request failed.",

                        "details":
                            last_error
                    }

        except requests.exceptions.Timeout as error:

            last_error = (
                "OpenRouter request timed out."
            )

            print(
                "OpenRouter timeout:",
                error
            )

        except requests.exceptions.ConnectionError as error:

            last_error = (
                "Could not connect to OpenRouter."
            )

            print(
                "OpenRouter connection error:",
                error
            )

        except requests.exceptions.RequestException as error:

            last_error = str(error)

            print(
                "OpenRouter request error:",
                error
            )

        except Exception as error:

            last_error = str(error)

            print(
                "Unexpected OpenRouter error:",
                error
            )

        if attempt < AI_MAX_RETRIES:

            wait_time = 1.0

            print(
                f"Retrying OpenRouter "
                f"in {wait_time} second..."
            )

            time.sleep(
                wait_time
            )

    return {

        "success":
            False,

        "error":
            "OpenRouter could not generate a response.",

        "details":
            last_error
    }


# ============================================================
# UNIFIED AI FUNCTION
# ============================================================

def call_ai(
    system_prompt,
    user_prompt,
    max_tokens=1000
):

    # ========================================================
    # 1. GEMINI PRIMARY
    # ========================================================

    print("")
    print(
        "Trying primary AI provider: Gemini"
    )

    gemini_result = call_gemini(

        system_prompt,

        user_prompt,

        max_tokens=max_tokens
    )

    if gemini_result.get(
        "success",
        False
    ):

        print(
            "AI provider used: Gemini"
        )

        return gemini_result

    print(
        "Gemini unavailable."
    )

    print(
        "Gemini details:",
        gemini_result.get(
            "details",
            gemini_result.get(
                "error",
                ""
            )
        )
    )

    # ========================================================
    # 2. OPENROUTER FALLBACK
    # ========================================================

    print(
        "Trying fallback AI provider: OpenRouter"
    )

    openrouter_result = call_openrouter(

        system_prompt,

        user_prompt,

        max_tokens=max_tokens
    )

    if openrouter_result.get(
        "success",
        False
    ):

        print(
            "AI provider used: OpenRouter"
        )

        return openrouter_result

    print(
        "Both AI providers failed."
    )

    return {

        "success":
            False,

        "error":
            "AI could not generate a response right now.",

        "details":
            (
                "Gemini: "
                +
                str(
                    gemini_result.get(
                        "details",
                        gemini_result.get(
                            "error",
                            ""
                        )
                    )
                )
                +
                " | OpenRouter: "
                +
                str(
                    openrouter_result.get(
                        "details",
                        openrouter_result.get(
                            "error",
                            ""
                        )
                    )
                )
            )
    }


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({

        "success":
            True,

        "status":
            "online",

        "message":
            "Vidora AI backend is running!"
    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/api/health")
def health():

    return jsonify({

        "success":
            True,

        "message":
            "Backend is healthy."
    })


# ============================================================
# YOUTUBE TRANSCRIPT
# ============================================================

YOUTUBETRANSCRIPT_API_URL = "https://www.youtubetranscript.dev/api/v2/transcribe"


def normalize_external_transcript(data):
    """Convert YouTubeTranscript.dev V2 responses into Vidora's format."""

    if not isinstance(data, dict):
        return None

    payload = data.get("data", {})
    if not isinstance(payload, dict):
        return None

    transcript_data = payload.get("transcript", {})

    # Current V2 response format:
    # data.transcript = {text, language, source, segments}
    if isinstance(transcript_data, dict):
        full_text = str(
            transcript_data.get("text", "") or ""
        ).strip()

        language = str(
            transcript_data.get("language", "") or ""
        ).strip()

        source = str(
            transcript_data.get("source", "") or ""
        ).strip()

        raw_segments = transcript_data.get("segments", [])

    # Compatibility with an older/alternate response where transcript
    # itself is a list of transcript segments.
    elif isinstance(transcript_data, list):
        full_text = ""
        language = str(payload.get("language", "") or "").strip()
        source = str(payload.get("source", "") or "").strip()
        raw_segments = transcript_data
    else:
        return None

    segments = []

    if isinstance(raw_segments, list):
        for item in raw_segments:
            if not isinstance(item, dict):
                continue

            text = str(item.get("text", "") or "").strip()
            if not text:
                continue

            try:
                start_ms = float(item.get("start", 0) or 0)
            except (TypeError, ValueError):
                start_ms = 0.0

            # V2 uses milliseconds for start/end.
            # Also accept seconds for compatibility if a provider returns
            # a duration field instead.
            try:
                end_ms = float(item.get("end", 0) or 0)
            except (TypeError, ValueError):
                end_ms = 0.0

            if end_ms > start_ms:
                duration = (end_ms - start_ms) / 1000.0
            else:
                try:
                    duration_value = float(
                        item.get("duration", item.get("dur", 0)) or 0
                    )
                except (TypeError, ValueError):
                    duration_value = 0.0

                duration = duration_value

            segments.append({
                "text": text,
                "start": start_ms / 1000.0,
                "duration": max(0.0, duration)
            })

    if not full_text and segments:
        full_text = " ".join(
            segment["text"] for segment in segments
        ).strip()

    if not full_text:
        return None

    # If the provider gives text but no segments, keep the transcript usable.
    if not segments:
        segments = [{
            "text": full_text,
            "start": 0.0,
            "duration": 0.0
        }]

    language_code = language

    return {
        "transcript": full_text,
        "segments": segments,
        "language": language,
        "language_code": language_code,
        "is_generated": source == "asr",
        "available_transcripts": []
    }


def fetch_transcript_external(video_id):
    """Fetch a YouTube transcript through the production transcript provider."""

    if not YOUTUBETRANSCRIPT_API_KEY:
        return {
            "success": False,
            "error": "YOUTUBETRANSCRIPT_API_KEY is not configured."
        }

    headers = {
        "Authorization": f"Bearer {YOUTUBETRANSCRIPT_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "video": video_id,
        "source": "auto",
        "format": {
            "timestamp": True,
            "paragraphs": False,
            "words": False
        }
    }

    try:
        response = requests.post(
            YOUTUBETRANSCRIPT_API_URL,
            headers=headers,
            json=payload,
            timeout=45
        )

        try:
            result = response.json()
        except ValueError:
            result = {}

        print(
            "YouTubeTranscript.dev status:",
            response.status_code
        )

        if response.status_code != 200:
            error_message = ""

            if isinstance(result, dict):
                error_value = (
                    result.get("message")
                    or result.get("error")
                    or result.get("detail")
                    or ""
                )

                if isinstance(error_value, dict):
                    error_message = (
                        error_value.get("message")
                        or error_value.get("detail")
                        or str(error_value)
                    )
                else:
                    error_message = str(error_value)

            # Give useful provider-specific messages in Render logs/API.
            status_messages = {
                401: "Invalid or unauthorized YouTubeTranscript.dev API key.",
                402: "YouTubeTranscript.dev credits/payment are required or exhausted.",
                404: "No captions were found for this video.",
                429: "YouTubeTranscript.dev rate limit exceeded."
            }

            if not error_message:
                error_message = status_messages.get(
                    response.status_code,
                    f"Transcript provider returned HTTP {response.status_code}."
                )

            print(
                "YouTubeTranscript.dev error:",
                response.status_code,
                error_message
            )

            return {
                "success": False,
                "status_code": response.status_code,
                "error": error_message
            }

        normalized = normalize_external_transcript(result)

        if not normalized:
            print(
                "YouTubeTranscript.dev returned HTTP 200 but no readable transcript."
            )
            return {
                "success": False,
                "status_code": response.status_code,
                "error": "Transcript provider returned no readable transcript."
            }

        print(
            "Transcript source: YouTubeTranscript.dev"
        )

        return {
            "success": True,
            **normalized
        }

    except requests.exceptions.Timeout:
        print(
            "YouTubeTranscript.dev request timed out."
        )
        return {
            "success": False,
            "error": "Transcript provider timed out."
        }

    except requests.exceptions.RequestException as error:
        print(
            "YouTubeTranscript.dev request error:",
            repr(error)
        )
        return {
            "success": False,
            "error": "Could not connect to transcript provider."
        }

    except Exception as error:
        print(
            "YouTubeTranscript.dev unexpected error:",
            repr(error)
        )
        return {
            "success": False,
            "error": str(error)
        }


def fetch_transcript_local(video_id):
    """Local YouTubeTranscriptApi fallback for development."""

    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)

    transcript_objects = []
    available_transcripts = []

    for transcript in transcript_list:
        transcript_objects.append(transcript)
        available_transcripts.append({
            "language": transcript.language,
            "language_code": transcript.language_code,
            "is_generated": transcript.is_generated
        })

    print(
        "Available transcripts:",
        available_transcripts
    )

    if not transcript_objects:
        raise Exception(
            "This video does not have captions or a transcript available."
        )

    preferred_languages = ["en", "hi", "gu"]
    selected_transcript = None

    # Preferred language + manual
    for language_code in preferred_languages:
        for transcript in transcript_objects:
            if (
                transcript.language_code == language_code
                and not transcript.is_generated
            ):
                selected_transcript = transcript
                break
        if selected_transcript:
            break

    # Preferred language + generated
    if selected_transcript is None:
        for language_code in preferred_languages:
            for transcript in transcript_objects:
                if (
                    transcript.language_code == language_code
                    and transcript.is_generated
                ):
                    selected_transcript = transcript
                    break
            if selected_transcript:
                break

    # Any manual transcript
    if selected_transcript is None:
        for transcript in transcript_objects:
            if not transcript.is_generated:
                selected_transcript = transcript
                break

    # Any transcript
    if selected_transcript is None:
        selected_transcript = transcript_objects[0]

    print(
        "Selected transcript:",
        selected_transcript.language,
        selected_transcript.language_code,
        "Generated:",
        selected_transcript.is_generated
    )

    fetched_transcript = selected_transcript.fetch()
    segments = []

    for snippet in fetched_transcript:
        text = str(snippet.text).strip()
        if not text:
            continue

        segments.append({
            "text": text,
            "start": float(snippet.start),
            "duration": float(snippet.duration)
        })

    full_text = " ".join(
        segment["text"] for segment in segments
    ).strip()

    if not full_text:
        raise Exception(
            "Captions were found, but no readable transcript text was available."
        )

    print(
        "Transcript source: local youtube-transcript-api"
    )

    return {
        "success": True,
        "transcript": full_text,
        "segments": segments,
        "language": selected_transcript.language,
        "language_code": selected_transcript.language_code,
        "is_generated": selected_transcript.is_generated,
        "available_transcripts": available_transcripts
    }


@app.route(
    "/api/transcript",
    methods=["POST"]
)
def get_transcript():

    data = request.get_json(silent=True)

    if not data or "url" not in data:
        return jsonify({
            "success": False,
            "error": "YouTube URL is required."
        }), 400

    url = str(data["url"]).strip()

    if not url:
        return jsonify({
            "success": False,
            "error": "Please paste a YouTube video URL."
        }), 400

    video_id = extract_video_id(url)

    if not video_id:
        return jsonify({
            "success": False,
            "error": (
                "Invalid YouTube URL. Please enter a valid "
                "YouTube video, Shorts, Live, Embed, or youtu.be link."
            )
        }), 400

    print(
        "Transcript request received for video:",
        video_id
    )

    # ------------------------------------------------------------
    # 1. Production provider
    # ------------------------------------------------------------
    external_result = fetch_transcript_external(video_id)

    if external_result.get("success"):
        return jsonify({
            "success": True,
            "video_id": video_id,
            "transcript": external_result["transcript"],
            "segments": external_result["segments"],
            "language": external_result.get("language", ""),
            "language_code": external_result.get("language_code", ""),
            "is_generated": external_result.get("is_generated", False),
            "available_transcripts": external_result.get(
                "available_transcripts", []
            ),
            "message": "Transcript fetched successfully."
        })

    provider_error = external_result.get(
        "error",
        "Unknown transcript provider error."
    )

    provider_status = external_result.get(
        "status_code"
    )

    print(
        "YouTubeTranscript.dev FAILED:",
        provider_status,
        provider_error
    )

    # ------------------------------------------------------------
    # 2. Local fallback ONLY when the production provider key is
    #    not configured. On Render, the external provider should be
    #    the source of truth so YouTube IP blocking is not involved.
    # ------------------------------------------------------------
    if not YOUTUBETRANSCRIPT_API_KEY:
        try:
            local_result = fetch_transcript_local(video_id)

            if local_result.get("success"):
                return jsonify({
                    "success": True,
                    "video_id": video_id,
                    "transcript": local_result["transcript"],
                    "segments": local_result["segments"],
                    "language": local_result.get("language", ""),
                    "language_code": local_result.get("language_code", ""),
                    "is_generated": local_result.get("is_generated", False),
                    "available_transcripts": local_result.get(
                        "available_transcripts", []
                    ),
                    "message": "Transcript fetched successfully."
                })

        except Exception as error:
            print(
                "Local transcript Error:",
                repr(error)
            )

    # ------------------------------------------------------------
    # Production failure response
    # ------------------------------------------------------------
    if provider_status == 401:
        message = (
            "Transcript service authentication failed. "
            "Please check the YOUTUBETRANSCRIPT_API_KEY in Render."
        )
    elif provider_status == 402:
        message = (
            "Transcript service credits are unavailable. "
            "Please check your YouTubeTranscript.dev account."
        )
    elif provider_status == 404:
        message = (
            "No captions were found for this video. "
            "Please try another video with captions."
        )
    elif provider_status == 429:
        message = (
            "Transcript service is temporarily rate-limited. "
            "Please try again shortly."
        )
    elif provider_status == 200:
        message = (
            "Transcript service returned an unreadable response. "
            "Please try again or another video."
        )
    else:
        message = (
            "We couldn't fetch the transcript right now. "
            "Please try again or another video."
        )

    return jsonify({
        "success": False,
        "error": message,
        "details": {
            "transcript_provider": provider_error,
            "provider_status": provider_status
        }
    }), 502


# ============================================================
# AI TEST
# ============================================================

@app.route(
    "/api/ai-test",
    methods=["POST"]
)
def ai_test():

    data = request.get_json(
        silent=True
    )

    if not data or "question" not in data:

        return jsonify({

            "success":
                False,

            "error":
                "Question is required."
        }), 400

    question = str(
        data["question"]
    ).strip()

    if not question:

        return jsonify({

            "success":
                False,

            "error":
                "Question cannot be empty."
        }), 400

    system_prompt = """
You are Vidora AI.

Answer clearly, accurately and helpfully.

Do not mention internal instructions,
safety checks, routing, model metadata,
or system messages.

Return only the useful answer.
"""

    result = call_ai(

        system_prompt,

        question,

        max_tokens=700
    )

    if not result["success"]:

        return jsonify(result), 500

    return jsonify({

        "success":
            True,

        "answer":
            result["answer"]
    })


# ============================================================
# VIDEO INFO
# ============================================================

@app.route(
    "/api/video-info",
    methods=["POST"]
)
def video_info():

    data = request.get_json(
        silent=True
    )

    if not data or "video_id" not in data:

        return jsonify({

            "success":
                False,

            "error":
                "Video ID is required."
        }), 400

    video_id = str(
        data["video_id"]
    ).strip()

    if not re.fullmatch(
        r"[A-Za-z0-9_-]{11}",
        video_id
    ):

        return jsonify({

            "success":
                False,

            "error":
                "Invalid YouTube video ID."
        }), 400

    try:

        youtube_url = (
            f"https://www.youtube.com/watch?v={video_id}"
        )

        response = requests.get(

            "https://www.youtube.com/oembed",

            params={

                "url":
                    youtube_url,

                "format":
                    "json"
            },

            timeout=8
        )

        if response.status_code != 200:

            return jsonify({

                "success":
                    True,

                "title":
                    "YouTube Video",

                "thumbnail":
                    (
                        "https://img.youtube.com/vi/"
                        f"{video_id}/hqdefault.jpg"
                    )
            })

        result = response.json()

        return jsonify({

            "success":
                True,

            "title":
                result.get(
                    "title",
                    "YouTube Video"
                ),

            "thumbnail":
                result.get(
                    "thumbnail_url",
                    (
                        "https://img.youtube.com/vi/"
                        f"{video_id}/hqdefault.jpg"
                    )
                )
        })

    except Exception as error:

        print(
            "Video Info Error:",
            error
        )

        return jsonify({

            "success":
                True,

            "title":
                "YouTube Video",

            "thumbnail":
                (
                    "https://img.youtube.com/vi/"
                    f"{video_id}/hqdefault.jpg"
                )
        })


# ============================================================
# AI FEATURE GENERATOR
# ============================================================

@app.route(
    "/api/ai-feature",
    methods=["POST"]
)
def ai_feature():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({

            "success":
                False,

            "error":
                "Request data is required."
        }), 400

    feature = str(
        data.get(
            "feature",
            ""
        )
    ).strip()

    transcript = str(
        data.get(
            "transcript",
            ""
        )
    ).strip()

    allowed_features = [

        "notes",
        "summary",
        "explain",
        "keypoints",
        "exam"
    ]

    if feature not in allowed_features:

        return jsonify({

            "success":
                False,

            "error":
                "Invalid AI feature."
        }), 400

    if not transcript:

        return jsonify({

            "success":
                False,

            "error":
                "Video transcript is required."
        }), 400

    # ========================================================
    # FEATURE TOKEN LIMITS
    # ========================================================

    feature_token_limits = {

        "notes":
            1200,

        "summary":
            600,

        "explain":
            1200,

        "keypoints":
            700,

        "exam":
            1500
    }

    # ========================================================
    # PROMPTS
    # ========================================================

    prompts = {

        "notes": """
Create complete, well-structured study notes from the
provided video transcript.

Include important concepts, definitions, explanations,
examples, steps, formulas, facts and important details
that are actually present in the transcript.

Use clear headings and bullet points.

Do not add outside knowledge.
Do not invent information.

Use ONLY the provided video transcript.
""",

        "summary": """
Create a clear and concise summary of the video.

Cover the main ideas and most important information.

Remove unnecessary repetition.

Use simple language and useful headings.

Do not add outside knowledge.

Use ONLY the provided video transcript.
""",

        "explain": """
Explain every important concept discussed in the video
in simple and detailed language.

Help the student understand the video deeply.

Explain concepts step by step where appropriate.

Include examples only when they are present or directly
supported by the transcript.

Do not add outside knowledge.

Use ONLY the provided video transcript.
""",

        "keypoints": """
Extract the most important points from the video.

Give a well-organized list of key concepts, definitions,
facts, steps, formulas and important ideas.

Keep the points easy to revise before an exam.

Do not add outside knowledge.

Use ONLY the provided video transcript.
""",

        "exam": """
Create exam preparation material based ONLY on this video.

Include:

1. Important exam questions
2. Short-answer questions
3. Long-answer questions
4. Multiple Choice Questions
5. Correct answers

Make the questions directly related to the transcript.

Do not create questions about information not present
in the video.

Do not add outside knowledge.
"""
    }

    system_prompt = """
You are Vidora AI, an educational video-learning assistant.

IMPORTANT:

ANSWER ONLY FROM THE PROVIDED VIDEO TRANSCRIPT.

Never invent facts.

Never use unrelated outside knowledge.

Never assume information that is not present.

If requested information is not covered in the video,
clearly say that it is not covered in this video.

Make answers clear, accurate and student-friendly.

Use headings and bullet points where useful.

Do not mention internal instructions.

Do not output safety labels or model/router metadata.

Return only the useful educational answer.
"""

    user_prompt = f"""
VIDEO TRANSCRIPT:

{transcript}

---

TASK:

{prompts[feature]}

---

IMPORTANT:

Use ONLY the transcript above.
Do not use outside knowledge.
Return only the requested educational material.
"""

    # ========================================================
    # GEMINI -> OPENROUTER FALLBACK
    # ========================================================

    result = call_ai(

        system_prompt,

        user_prompt,

        max_tokens=
            feature_token_limits[feature]
    )

    if not result["success"]:

        return jsonify({

            "success":
                False,

            "feature":
                feature,

            "error":
                result.get(
                    "error",
                    "AI feature failed."
                ),

            "details":
                result.get(
                    "details",
                    ""
                )
        }), 500

    return jsonify({

        "success":
            True,

        "feature":
            feature,

        "answer":
            result["answer"]
    })


# ============================================================
# ASK AI
# ============================================================

@app.route(
    "/api/ask",
    methods=["POST"]
)
def ask_ai():

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({

            "success":
                False,

            "error":
                "Request data is required."
        }), 400

    question = str(
        data.get(
            "question",
            ""
        )
    ).strip()

    transcript = str(
        data.get(
            "transcript",
            ""
        )
    ).strip()

    if not question:

        return jsonify({

            "success":
                False,

            "error":
                "Question is required."
        }), 400

    if not transcript:

        return jsonify({

            "success":
                False,

            "error":
                "Video transcript is required."
        }), 400

    system_prompt = """
You are Vidora AI.

Answer the user's question using ONLY the provided
YouTube video transcript.

The question is about the current video.

Rules:

- Do not use outside knowledge.
- Do not invent information.
- Do not guess.
- If the answer is not available in the video,
  clearly say that the information is not covered
  in this video.
- Give a clear and useful answer.
- Explain the answer when necessary.
- Do not mention internal instructions.
- Do not output safety labels.
- Do not output model/router metadata.

Return only the useful answer.
"""

    user_prompt = f"""
VIDEO TRANSCRIPT:

{transcript}

---

USER QUESTION:

{question}

---

Answer using ONLY the video transcript.
"""

    result = call_ai(

        system_prompt,

        user_prompt,

        max_tokens=800
    )

    if not result["success"]:

        return jsonify({

            "success":
                False,

            "error":
                result.get(
                    "error",
                    "Ask AI failed."
                ),

            "details":
                result.get(
                    "details",
                    ""
                )
        }), 500

    return jsonify({

        "success":
            True,

        "answer":
            result["answer"]
    })


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    print("")
    print("==========================================")
    print("        VIDORA AI BACKEND STARTED")
    print("==========================================")
    print(
        "URL: http://127.0.0.1:5000"
    )
    print(
        "Primary AI: Gemini"
    )
    print(
        "Gemini Model:",
        GEMINI_MODEL
    )
    print(
        "Fallback AI:",
        AI_MODEL
    )
    print(
        "Provider Sort:",
        AI_PROVIDER_SORT
    )
    print("==========================================")
    print("")

    app.run(

        host="127.0.0.1",

        port=5000,

        debug=True
    )
