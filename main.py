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

@app.post("/render-scene")
async def render_scene(data: SceneRequest):
    req_id = str(uuid.uuid4())[:8]
    img_path = f"/tmp/{req_id}_input.jpg"
    audio_path = f"/tmp/{req_id}_input.wav"
    output_path = f"/tmp/{req_id}_scene_{data.scene_number}.mp4"

    try:
        # 1. Save Image (Handles both Base64 and URL)
        if data.image_base64:
            with open(img_path, "wb") as f:
                f.write(base64.b64decode(data.image_base64))
        elif data.image_url and data.image_url.startswith("http"):
            async with httpx.AsyncClient() as client:
                resp = await client.get(data.image_url)
                with open(img_path, "wb") as f:
                    f.write(resp.content)
        else:
            raise HTTPException(status_code=400, detail="Valid image_base64 or image_url is required")

        # 2. Save Audio (Handles both Base64 and URL)
        if data.audio_base64:
            with open(audio_path, "wb") as f:
                f.write(base64.b64decode(data.audio_base64))
        elif data.audio_url and data.audio_url.startswith("http"):
            async with httpx.AsyncClient() as client:
                resp = await client.get(data.audio_url)
                with open(audio_path, "wb") as f:
                    f.write(resp.content)
        else:
            raise HTTPException(status_code=400, detail="Audio is required")

        # 3. Run FFmpeg: Ken Burns Zoom + Audio sync
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_path,
            "-i", audio_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='min(zoom+0.0015,1.25)':d=125:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080",
            "-c:v", "libx264", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
            "-shortest",
            output_path
        ]
        subprocess.run(cmd, check=True)

        # 4. Read Rendered Binary Video
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
        # Cleanup temporary files
        for p in [img_path, audio_path, output_path]:
            if os.path.exists(p):
                os.remove(p)
