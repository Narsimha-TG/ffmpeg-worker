from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import base64
import uuid
import os
import asyncio

app = FastAPI()

class SceneRequest(BaseModel):
    image_base64: str
    audio_base64: str
    scene_number: int = 1

@app.get("/")
def home():
    return {"status": "running", "worker": "FFmpeg Video Renderer"}

@app.post("/render-scene")
async def render_scene(data: SceneRequest):
    req_id = str(uuid.uuid4())[:8]
    img_path = f"/tmp/{req_id}_input.jpg"
    audio_path = f"/tmp/{req_id}_input.wav"
    output_path = f"/tmp/{req_id}_scene_{data.scene_number}.mp4"

    try:
        # 1. Decode & Save Image
        with open(img_path, "wb") as f:
            f.write(base64.b64decode(data.image_base64))

        # 2. Decode & Save Audio
        with open(audio_path, "wb") as f:
            f.write(base64.b64decode(data.audio_base64))

        # 3. Super Fast FFmpeg 720p Render
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_path,
            "-i", audio_path,
            "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"FFmpeg error: {stderr.decode('utf-8', errors='ignore')}")

        with open(output_path, "rb") as f:
            video_bytes = f.read()

        return {
            "status": "success",
            "scene_number": data.scene_number,
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
