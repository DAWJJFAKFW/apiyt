from flask import Flask, request, jsonify
import subprocess

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

    cmd = ["yt-dlp", "-q", "-f", "bestaudio", "--get-url", yt_url]

    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=25).decode(errors="ignore")
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if not lines:
            return jsonify({"ok": False, "error": "empty output"}), 500

        audio_url = lines[-1]

        if not audio_url.startswith("http"):
            return jsonify({"ok": False, "error": "no valid url found", "raw": out}), 500

        return jsonify({"ok": True, "audio_url": audio_url})

    except subprocess.CalledProcessError as e:
        return jsonify({"ok": False, "error": e.output.decode(errors="ignore")}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
