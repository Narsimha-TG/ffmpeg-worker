from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import subprocess
import base64
import uuid
import os
import gc
import urllib.request

app = FastAPI()

class SceneRequest(BaseModel):
    image_url: str
    audio_base64: str
    scene_number: int = 1

class ConcatRequest(BaseModel):
    videos_base64: List[str]

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
        return round(float(result.stdout.strip()), 2)
    except Exception:
        return 6.0

@app.get("/")
def home():
    return {"status": "running", "worker": "FFmpeg Master Renderer"}

@app.post("/render-scene")
def render_scene(data: SceneRequest):
    req_id = str(uuid.uuid4())[:8]
    img_path = f"/tmp/{req_id}_in.jpg"
    audio_path = f"/tmp/{req_id}_in.wav"
    output_path = f"/tmp/{req_id}_out.mp4"

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(data.image_url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as response:
            img_bytes = response.read()

        if len(img_bytes) < 2000:
            raise Exception(f"Downloaded image is too small (size: {len(img_bytes)} bytes)")

        with open(img_path, "wb") as f:
            f.write(img_bytes)

        audio_bytes = base64.b64decode(data.audio_base64)
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        data.audio_base64 = ""
        del img_bytes, audio_bytes
        gc.collect()

        duration = get_audio_duration(audio_path)

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

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
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

@app.post("/concat-videos")
def concat_videos(data: ConcatRequest):
    req_id = str(uuid.uuid4())[:8]
    list_file_path = f"/tmp/{req_id}_list.txt"
    output_path = f"/tmp/{req_id}_final.mp4"
    video_files = []

    try:
        # 1. ప్రతి వీడియో బేస్‌64ని తాత్కాలిక ఫైల్స్‌గా సేవ్ చేయడం
        for idx, v_b64 in enumerate(data.videos_base64):
            v_path = f"/tmp/{req_id}_v_{idx}.mp4"
            v_bytes = base64.b64decode(v_b64)
            with open(v_path, "wb") as f:
                f.write(v_bytes)
            video_files.append(v_path)

        # 2. FFmpeg concat కోసం లిస్ట్ ఫైల్ తయారు చేయడం
        with open(list_file_path, "w") as f:
            for v_path in video_files:
                f.write(f"file '{v_path}'\n")

        # 3. అన్ని వీడియోలను కలపడం
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file_path,
            "-c", "copy",
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise Exception(f"FFmpeg Concat failed: {result.stderr}")

        with open(output_path, "rb") as f:
            final_bytes = f.read()

        return {
            "status": "success",
            "final_video_base64": base64.b64encode(final_bytes).decode("utf-8")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(list_file_path):
            os.remove(list_file_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        for v_path in video_files:
            if os.path.exists(v_path):
                os.remove(v_path)
        gc.collect()
