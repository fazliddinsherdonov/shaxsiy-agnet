import os
import tempfile
import subprocess

def convert_to_videonote(input_bytes: bytes, size: int = 384) -> bytes | None:
    """
    Har qanday videoni Telegram dumaloq video formatiga o'tkazish:
    - Kvadrat kesish (crop)
    - 384x384 o'lcham
    - MP4 format
    - Max 60 soniya
    """
    input_tmp = None
    output_tmp = None
    try:
        # Kiruvchi faylni vaqtincha saqlash
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(input_bytes)
            input_tmp = f.name

        # Chiquvchi fayl
        output_tmp = tempfile.mktemp(suffix="_note.mp4")

        # ffmpeg buyrug'i:
        # - vf: kvadrat kesish va o'lchamni o'zgartirish
        # - t 60: max 60 soniya
        # - an: audio olib tashlash (video note uchun shart emas)
        cmd = [
            "ffmpeg",
            "-i", input_tmp,
            "-vf", f"crop=min(iw\\,ih):min(iw\\,ih),scale={size}:{size}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "28",
            "-t", "60",
            "-movflags", "+faststart",
            "-y",
            "-loglevel", "quiet",
            output_tmp
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=60)

        if result.returncode != 0:
            print(f"ffmpeg xatosi: {result.stderr.decode()}")
            return None

        with open(output_tmp, "rb") as f:
            return f.read()

    except FileNotFoundError:
        print("❌ ffmpeg o'rnatilmagan! O'rnatish: choco install ffmpeg")
        return None
    except Exception as e:
        print(f"Konvertatsiya xatosi: {e}")
        return None
    finally:
        if input_tmp and os.path.exists(input_tmp):
            os.unlink(input_tmp)
        if output_tmp and os.path.exists(output_tmp):
            os.unlink(output_tmp)


def is_ffmpeg_installed() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except:
        return False
