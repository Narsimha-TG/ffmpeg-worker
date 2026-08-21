from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess
import httpx
import base64
import uuid
import os

app = FastAPI()

class SceneRequest(BaseModel):
    image_url: str | None = None
    image_base64: str | None = None
    audio_base64: str | None = None
    audio_url: str | None = None
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
        # 1. Download/Save Image (With 60s timeout for Pollinations)
        if data.image_base64:
            with open(img_path, "wb") as f:
                f.write(base64.b64decode(data.image_base64))
        elif data.image_url and data.image_url.startswith("http"):
            headers = {"User-Agent": "Mozilla/5.0"}
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(data.image_url, headers=headers)
                if resp.status_code != 200:
                    raise Exception(f"Failed to fetch image: HTTP {resp.status_code}")
                with open(img_path, "wb") as f:
                    f.write(resp.content)
        else:
            raise HTTPException(status_code=400, detail="Valid image is required")

        # 2. Download/Save Audio
        if data.audio_base64:
            with open(audio_path, "wb") as f:
                f.write(base64.b64decode(data.audio_base64))
        elif data.audio_url and data.audio_url.startswith("http"):
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(data.audio_url)
                with open(audio_path, "wb") as f:
                    f.write(resp.content)
        else:
            raise HTTPException(status_code=400, detail="Valid audio is required")

        # 3. FFmpeg Ken Burns 1080p Render
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_path,
            "-i", audio_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='min(zoom+0.0015,1.2)':d=125:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=25",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path
        ]
        
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")

        # 4. Return Video Base64
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
