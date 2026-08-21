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
        return 6.0

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
        # 1. Base64 డీకోడ్ మరియు సైజ్ చెక్
        img_bytes = base64.b64decode(data.image_base64)
        audio_bytes = base64.b64decode(data.audio_base64)

        if len(img_bytes) < 2000:
            raise Exception(f"Image data is too small or corrupt (size: {len(img_bytes)} bytes)")
        if len(audio_bytes) < 2000:
            raise Exception(f"Audio data is too small or corrupt (size: {len(audio_bytes)} bytes)")

        with open(img_path, "wb") as f:
            f.write(img_bytes)

        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        # మెమరీ క్లియర్
        data.image_base64 = ""
        data.audio_base64 = ""
        del img_bytes, audio_bytes
        gc.collect()

        # 2. ఆడియో నిడివిని లెక్కించడం
        duration = get_audio_duration(audio_path)

        # 3. వేగవంతమైన FFmpeg ఎన్‌కోడింగ్
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
            "-b:a", "96k",
            "-t", str(duration),
            "-movflags", "+faststart",
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)

        if result.returncode != 0:
            raise Exception(f"FFmpeg failed: {result.stderr}")

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
