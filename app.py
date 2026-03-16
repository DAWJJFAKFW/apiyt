from flask import Flask, request, jsonify
import subprocess

UNSUPPORTED_MIME_MARKERS = (
    "mime=audio/webm",
    "mime=audio/opus",
)

FORMAT_CANDIDATES = [
    "bestaudio[ext=m4a]/bestaudio[acodec*=mp4a]",
    "bestaudio[ext=mp3]/bestaudio[acodec*=mp3]",
    "bestaudio",
]


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

app = Flask(__name__)

@app.route("/")
def home():
    return "ok"

@app.route("/audio")
def audio():
    video_id = request.args.get("videoId", "").strip()
    if not video_id:
        return jsonify({"ok": False, "error": "missing videoId"}), 400

    video_id = "".join(c for c in video_id if c.isalnum() or c in ["-", "_"])
    if not video_id:
        return jsonify({"ok": False, "error": "invalid videoId"}), 400

    yt_url = f"https://www.youtube.com/watch?v={video_id}"

    ok, audio_url, err = get_audio_url(yt_url)
    if not ok:
        return jsonify({
            "ok": False,
            "error": err or "audio not available",
            "hint": "Some videos are restricted, geo-blocked, live-only, or only offer codecs unsupported by MTA.",
        }), 500

    return jsonify({"ok": True, "audio_url": audio_url})
