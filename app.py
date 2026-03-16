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

    cmd = ["yt-dlp", "-f", "bestaudio", "--get-url", yt_url]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=25).decode().strip()
        if not out:
            return jsonify({"ok": False, "error": "empty audio url"}), 500
        return jsonify({"ok": True, "audio_url": out})
    except subprocess.CalledProcessError as e:
        return jsonify({"ok": False, "error": e.output.decode(errors="ignore")}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500