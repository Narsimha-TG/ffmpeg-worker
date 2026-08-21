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
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(result.stdout.strip())
    except Exception:
        return 5.0  # Fallback duration if probe fails

@app.get("/")
def home():
    return {"status": "running", "worker": "FFmpeg Stable Worker"}

@app.post("/render-scene")
def render_scene(data: SceneRequest):
    req_id = str(uuid.uuid4())[:8]
    img_path = f"/tmp/{req_id}_in.jpg"
    audio_path = f"/tmp/{req_id}_in.wav"
    output_path = f"/tmp/{req_id}_out.mp4"

    try:
        # 1. Save Base64 to disk
        with open(img_path, "wb") as f:
            f.write(base64.b64decode(data.image_base64))

        with open(audio_path, "wb") as f:
            f.write(base64.b64decode(data.audio_base64))

        # Free memory
        data.image_base64 = ""
        data.audio_base64 = ""
        gc.collect()

        # 2. Get exact audio duration
        duration = get_audio_duration(audio_path)

        # 3. Explicit duration render (Super fast & No Infinite Loop)
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-framerate", "24",
            "-t", str(duration),
            "-i", img_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-threads", "2",
            output_path
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)

        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr.decode('utf-8', errors='ignore')}")

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
