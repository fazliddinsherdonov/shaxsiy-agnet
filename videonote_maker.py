import os
import asyncio
import tempfile
import subprocess

async def text_to_videonote(text: str, groq_client) -> bytes | None:
    """
    Matnni dumaloq video xabarga aylantirish:
    1. Groq TTS -> audio
    2. ffmpeg -> audio + black background -> dumaloq video (mp4)
    """
    tmp_audio = None
    tmp_video = None
    try:
        # 1. Matnni ovozga aylantirish
        response = groq_client.audio.speech.create(
            model="canopylabs/orpheus-v1-english",
            voice="sarah",
            input=text,
            response_format="wav",
        )
        audio_bytes = response.content

        # Vaqtincha audio fayl
        tmp_audio = tempfile.mktemp(suffix=".wav")
        with open(tmp_audio, "wb") as f:
            f.write(audio_bytes)

        # 2. Audio uzunligini aniqlash
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", tmp_audio],
            capture_output=True, text=True
        )
        duration = float(result.stdout.strip()) if result.stdout.strip() else 10.0

        # 3. ffmpeg: audio + qora fon + aylana mask -> mp4
        tmp_video = tempfile.mktemp(suffix=".mp4")
        
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=black:size=384x384:duration={duration}:rate=30",
            "-i", tmp_audio,
            "-filter_complex",
            "[0:v]geq=lum='if(lte(hypot(X-W/2\\,Y-H/2)\\,W/2)\\,lum(X\\,Y)\\,0)':cb='if(lte(hypot(X-W/2\\,Y-H/2)\\,W/2)\\,cb(X\\,Y)\\,128)':cr='if(lte(hypot(X-W/2\\,Y-H/2)\\,W/2)\\,cr(X\\,Y)\\,128)'[v]",
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-shortest",
            "-pix_fmt", "yuv420p",
            tmp_video
        ]
        
        proc = subprocess.run(ffmpeg_cmd, capture_output=True)
        
        if proc.returncode != 0:
            # Sodda versiya - faqat qora fon
            ffmpeg_simple = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=0x1a1a2e:size=384x384:duration={duration}:rate=25",
                "-i", tmp_audio,
                "-c:v", "libx264", "-c:a", "aac",
                "-shortest", "-pix_fmt", "yuv420p",
                tmp_video
            ]
            subprocess.run(ffmpeg_simple, capture_output=True)

        if os.path.exists(tmp_video):
            with open(tmp_video, "rb") as f:
                return f.read()
        return None

    except Exception as e:
        print(f"Video note tayyorlash xatosi: {e}")
        return None
    finally:
        if tmp_audio and os.path.exists(tmp_audio): os.unlink(tmp_audio)
        if tmp_video and os.path.exists(tmp_video): os.unlink(tmp_video)


async def make_avatar_videonote(text: str, groq_client, avatar_path: str = None) -> bytes | None:
    """
    Avatar rasm bilan dumaloq video (ixtiyoriy)
    """
    tmp_audio = None
    tmp_video = None
    try:
        response = groq_client.audio.speech.create(
            model="canopylabs/orpheus-v1-english",
            voice="sarah",
            input=text,
            response_format="wav",
        )
        audio_bytes = response.content
        tmp_audio = tempfile.mktemp(suffix=".wav")
        with open(tmp_audio, "wb") as f:
            f.write(audio_bytes)

        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", tmp_audio],
            capture_output=True, text=True
        )
        duration = float(result.stdout.strip()) if result.stdout.strip() else 10.0
        tmp_video = tempfile.mktemp(suffix=".mp4")

        if avatar_path and os.path.exists(avatar_path):
            # Avatar rasmli versiya
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", avatar_path,
                "-i", tmp_audio,
                "-filter_complex",
                "[0:v]scale=384:384,geq=lum='if(lte(hypot(X-W/2\\,Y-H/2)\\,W/2)\\,lum(X\\,Y)\\,0)':cb='if(lte(hypot(X-W/2\\,Y-H/2)\\,W/2)\\,cb(X\\,Y)\\,128)':cr='if(lte(hypot(X-W/2\\,Y-H/2)\\,W/2)\\,cr(X\\,Y)\\,128)'[v]",
                "-map", "[v]", "-map", "1:a",
                "-c:v", "libx264", "-c:a", "aac",
                "-t", str(duration), "-pix_fmt", "yuv420p",
                tmp_video
            ]
        else:
            # Gradient fon
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"color=c=0x2C3E50:size=384x384:duration={duration}:rate=25",
                "-i", tmp_audio,
                "-c:v", "libx264", "-c:a", "aac",
                "-shortest", "-pix_fmt", "yuv420p",
                tmp_video
            ]
        
        subprocess.run(cmd, capture_output=True)

        if os.path.exists(tmp_video):
            with open(tmp_video, "rb") as f:
                return f.read()
        return None

    except Exception as e:
        print(f"Avatar video xatosi: {e}")
        return None
    finally:
        if tmp_audio and os.path.exists(tmp_audio): os.unlink(tmp_audio)
        if tmp_video and os.path.exists(tmp_video): os.unlink(tmp_video)
