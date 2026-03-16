from flask import Flask, request, jsonify, send_from_directory
import subprocess
from pathlib import Path

UNSUPPORTED_MIME_MARKERS = (
    "mime=audio/webm",
    "mime=audio/opus",
)

FORMAT_CANDIDATES = [
    "bestaudio[ext=m4a]/bestaudio[acodec*=mp4a]",
    "bestaudio[ext=mp3]/bestaudio[acodec*=mp3]",
    "bestaudio",
]

PROXY_FORMAT = "bestaudio[ext=m4a]/bestaudio[acodec*=mp4a]/bestaudio"
MAX_CACHE_FILES = 80

CACHE_DIR = Path(__file__).resolve().parent / "cache_audio"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def is_mta_friendly_url(url: str) -> bool:
    lowered = url.lower()
    for marker in UNSUPPORTED_MIME_MARKERS:
        if marker in lowered:
            return False
    return lowered.startswith("http")


def get_audio_url(yt_url: str):
    """Try multiple format selectors and return the first MTA-friendly direct URL."""
    last_error = "yt-dlp failed"

    for fmt in FORMAT_CANDIDATES:
        cmd = [
            "yt-dlp",
            "-q",
            "--no-warnings",
            "--no-playlist",
            "--socket-timeout",
            "15",
            "--extractor-retries",
            "2",
            "--geo-bypass",
            "-f",
            fmt,
            "--get-url",
            yt_url,
        ]

        try:
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=25).decode(errors="ignore")
            lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
            if not lines:
                last_error = "empty output"
                continue

            candidate = lines[-1]
            if is_mta_friendly_url(candidate):
                return True, candidate, None

            last_error = "unsupported audio codec/container for MTA"
        except subprocess.CalledProcessError as e:
            last_error = e.output.decode(errors="ignore").strip() or "yt-dlp error"
        except subprocess.TimeoutExpired:
            last_error = "yt-dlp timeout"
        except Exception as e:
            last_error = str(e)

    return False, None, last_error


def prune_cache():
    files = [p for p in CACHE_DIR.iterdir() if p.is_file()]
    if len(files) <= MAX_CACHE_FILES:
        return

    files.sort(key=lambda p: p.stat().st_mtime)
    to_remove = files[: max(0, len(files) - MAX_CACHE_FILES)]
    for p in to_remove:
        try:
            p.unlink()
        except Exception:
            pass


def find_cached_audio(video_id: str):
    # Prefer stable formats when multiple cached variants exist.
    preferred_ext = ["m4a", "mp3", "aac", "ogg", "webm"]
    for ext in preferred_ext:
        p = CACHE_DIR / f"{video_id}.{ext}"
        if p.is_file():
            return p.name

    for p in CACHE_DIR.glob(f"{video_id}.*"):
        if p.is_file():
            return p.name
    return None


def download_audio_to_cache(video_id: str):
    cached = find_cached_audio(video_id)
    if cached:
        return True, cached, None

    yt_url = f"https://www.youtube.com/watch?v={video_id}"
    output_tpl = str(CACHE_DIR / "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--no-playlist",
        "--geo-bypass",
        "--socket-timeout",
        "15",
        "--extractor-retries",
        "3",
        "--retries",
        "3",
        "--fragment-retries",
        "3",
        "-f",
        PROXY_FORMAT,
        "-o",
        output_tpl,
        yt_url,
    ]

    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=240)
    except subprocess.CalledProcessError as e:
        return False, None, e.output.decode(errors="ignore").strip() or "yt-dlp error"
    except subprocess.TimeoutExpired:
        return False, None, "yt-dlp timeout"
    except Exception as e:
        return False, None, str(e)

    cached = find_cached_audio(video_id)
    if not cached:
        return False, None, "cache file not found"

    try:
        # Touch file mtime to keep recently used items in cache.
        path = CACHE_DIR / cached
        path.touch()
        # Keep cache bounded.
        prune_cache()
    except Exception:
        pass

    return True, cached, None

app = Flask(__name__)

@app.route("/")
def home():
    return "ok"


@app.route("/media/<path:filename>")
def media(filename):
    return send_from_directory(CACHE_DIR, filename, conditional=True)

@app.route("/audio")
def audio():
    video_id = request.args.get("videoId", "").strip()
    if not video_id:
        return jsonify({"ok": False, "error": "missing videoId"}), 400

    video_id = "".join(c for c in video_id if c.isalnum() or c in ["-", "_"])
    if not video_id:
        return jsonify({"ok": False, "error": "invalid videoId"}), 400

    # Primary mode: serve cached/proxied media from this server for stable playback in MTA.
    ok_cache, cached_name, cache_err = download_audio_to_cache(video_id)
    if ok_cache and cached_name:
        media_url = request.host_url.rstrip("/") + "/media/" + cached_name
        return jsonify({"ok": True, "audio_url": media_url, "source": "proxy-cache"})

    return jsonify({
        "ok": False,
        "error": cache_err or "audio cache failed",
        "hint": "No se pudo generar audio estable en cache. Intenta otra cancion o reintenta en unos segundos.",
    }), 500
