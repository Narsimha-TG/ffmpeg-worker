from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import base64
import uuid
import os
import gc

app = FastAPI()

class SceneRequest(BaseModel):
    image_base64: str
    audio_base64: str
    scene_number: int = 1

def get_audio_duration(audio_path: str) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        dur = float(result.stdout.strip())
        return round(dur, 2)
    except Exception:
        return 5.0

@app.get("/")
def home():
    return {"status": "running", "worker": "FFmpeg Stable Renderer"}

@app.post("/render-scene")
def render_scene(data: SceneRequest):
    req_id = str(uuid.uuid4())[:8]
    img_path = f"/tmp/{req_id}_in.jpg"
    audio_path = f"/tmp/{req_id}_in.wav"
    output_path = f"/tmp/{req_id}_out.mp4"

    try:
        # 1. Save and validate image
        img_bytes = base64.b64decode(data.image_base64)
        if len(img_bytes) < 1000:
            raise Exception(f"Invalid image received from n8n (size: {len(img_bytes)} bytes)")

        with open(img_path, "wb") as f:
            f.write(img_bytes)

        # 2. Save audio
        with open(audio_path, "wb") as f:
            f.write(base64.b64decode(data.audio_base64))

        data.image_base64 = ""
        data.audio_base64 = ""
        gc.collect()

        # 3. Get exact duration
        duration = get_audio_duration(audio_path)

        # 4. Standard FFmpeg video render
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", img_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-t", str(duration),
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")

        with open(output_path, "rb") as f:
            video_bytes = f.read()

        return {
            "status": "success",
            "scene_number": data.scene_number,
            "duration": duration,
            "video_base64": base64.b64encode(video_bytes).decode("utf-8")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for p in [img_path, audio_path, output_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        gc.collect()
