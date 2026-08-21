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

class SceneItem(BaseModel):
    image_url: str
    audio_base64: str

class FullStoryRequest(BaseModel):
    scenes: List[SceneItem]

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
    return {"status": "running", "worker": "FFmpeg Full Story Renderer"}

@app.post("/generate-full-story")
def generate_full_story(data: FullStoryRequest):
    req_id = str(uuid.uuid4())[:8]
    list_file_path = f"/tmp/{req_id}_list.txt"
    final_output_path = f"/tmp/{req_id}_final.mp4"
    scene_videos = []

    try:
        # 1. ప్రతి సీన్‌ను విడివిడిగా రెండర్ చేసి వీడియో ఫైల్‌గా మార్చడం
        for idx, scene in enumerate(data.scenes):
            img_path = f"/tmp/{req_id}_s{idx}_img.jpg"
            audio_path = f"/tmp/{req_id}_s{idx}_audio.wav"
            scene_out_path = f"/tmp/{req_id}_s{idx}_out.mp4"

            # ఇమేజ్ డౌన్లోడ్
            headers = {'User-Agent': 'Mozilla/5.0'}
            req = urllib.request.Request(scene.image_url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as response:
                img_bytes = response.read()
            with open(img_path, "wb") as f:
                f.write(img_bytes)

            # ఆడియో సేవ్
            audio_bytes = base64.b64decode(scene.audio_base64)
            with open(audio_path, "wb") as f:
                f.write(audio_bytes)

            duration = get_audio_duration(audio_path)

            # FFmpeg సీన్ రెండరింగ్
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
                scene_out_path
            ]

            res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            if res.returncode != 0:
                raise Exception(f"Scene {idx+1} render failed: {res.stderr}")

            scene_videos.append(scene_out_path)

            # తాత్కాలిక ఇమేజ్/ఆడియో క్లీనప్
            if os.path.exists(img_path): os.remove(img_path)
            if os.path.exists(audio_path): os.remove(audio_path)

        # 2. అన్ని సీన్ల వీడియోలను కాంకాట్ (Concat) చేయడానికి లిస్ట్ తయారు చేయడం
        with open(list_file_path, "w") as f:
            for v_path in scene_videos:
                f.write(f"file '{v_path}'\n")

        # 3. అన్నింటినీ కలిపి ఒకే ఫైనల్ వీడియో చేయడం
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file_path,
            "-c", "copy",
            final_output_path
        ]

        concat_res = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=120)
        if concat_res.returncode != 0:
            raise Exception(f"FFmpeg Concat failed: {concat_res.stderr}")

        with open(final_output_path, "rb") as f:
            final_bytes = f.read()

        return {
            "status": "success",
            "final_video_base64": base64.b64encode(final_bytes).decode("utf-8")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # క్లీనప్
        if os.path.exists(list_file_path): os.remove(list_file_path)
        if os.path.exists(final_output_path): os.remove(final_output_path)
        for v_path in scene_videos:
            if os.path.exists(v_path):
                try: os.remove(v_path)
                except: pass
        gc.collect()
