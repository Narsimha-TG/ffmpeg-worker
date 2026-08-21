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

@app.get("/")
def home():
    return {"status": "running"}

@app.post("/render-scene")
def render_scene(data: SceneRequest):
    req_id = str(uuid.uuid4())[:8]
    img_path = f"/tmp/{req_id}_in.jpg"
    audio_path = f"/tmp/{req_id}_in.wav"
    output_path = f"/tmp/{req_id}_out.mp4"

    try:
        with open(img_path, "wb") as f:
            f.write(base64.b64decode(data.image_base64))
        with open(audio_path, "wb") as f:
            f.write(base64.b64decode(data.audio_base64))

        # Direct simple 1-fps encoding without infinite loop
        cmd = [
            "ffmpeg", "-y",
            "-framerate", "1",
            "-i", img_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "96k",
            "-shortest",
            output_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if res.returncode != 0:
            raise Exception(res.stderr.decode('utf-8', errors='ignore'))

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
                os.remove(p)
        gc.collect()
