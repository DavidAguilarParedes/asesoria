"""Monta el video final: acelera las esperas del agente, agrega música suave y lo pasa a .mp4.

    uv run --no-project --with numpy --with pillow python scripts/montar_video.py video/

Lee el .webm y esperas.json que deja grabar_video.py. Necesita ffmpeg en el PATH.
La música se genera aquí mismo (acordes suaves con ondas seno): no tiene derechos de autor.
"""

import argparse
import json
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

SPEED = 4  # las esperas del agente se ven 4 veces más rápido
RATE = 44100
FONTS = ["/mnt/c/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def segments(duration: float, waits: list[list[float]]) -> list[tuple[float, float, bool]]:
    """Parte el video en tramos normales y tramos de espera (que se aceleran)."""
    parts, cursor = [], 0.0
    for start, end in sorted(waits):
        start, end = max(start, cursor), min(end, duration)
        if end - start < 1.5:  # esperas cortas quedan igual
            continue
        if start > cursor:
            parts.append((cursor, start, False))
        parts.append((start, end, True))
        cursor = end
    if cursor < duration:
        parts.append((cursor, duration, False))
    return parts


def duration_of(path: Path) -> float:
    out = subprocess.run(["ffmpeg", "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = out.split("Duration: ")[1].split(",")[0].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def badge(path: Path) -> None:
    """Etiqueta "Acelerado ×4" que se ve mientras el video va acelerado."""
    font_file = next((f for f in FONTS if Path(f).exists()), None)
    font = ImageFont.truetype(font_file, 26) if font_file else ImageFont.load_default()
    text = f"Acelerado ×{SPEED}"
    w = int(ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(text, font=font)) + 32
    img = Image.new("RGBA", (w, 50), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, w - 1, 49), radius=12, fill=(24, 42, 44, 220))
    draw.text((16, 9), text, font=font, fill=(255, 255, 255, 255))
    img.save(path)


def speed_up(video: Path, parts, out: Path) -> None:
    tag = out.with_name("acelerado.png")
    badge(tag)
    n_fast = sum(1 for p in parts if p[2])
    filters = [f"[1:v]split={n_fast}" + "".join(f"[b{j}]" for j in range(n_fast))] if n_fast else []
    labels, j = [], 0
    for i, (start, end, fast) in enumerate(parts):
        if fast:
            filters.append(f"[0:v]trim={start}:{end},setpts=(PTS-STARTPTS)/{SPEED}[s{i}]")
            filters.append(f"[s{i}][b{j}]overlay=W-w-28:24:shortest=1[v{i}]")
            j += 1
        else:
            filters.append(f"[0:v]trim={start}:{end},setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"[v{i}]")
    graph = ";".join(filters) + ";" + "".join(labels) + f"concat=n={len(parts)}:v=1:a=0[v]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-loop", "1", "-i", str(tag),
                    "-filter_complex", graph,
                    "-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-r", "30", str(out)], check=True)


def note(freq: float, seconds: float) -> np.ndarray:
    """Una nota suave: seno con su octava, vibrato leve y envolvente lenta."""
    t = np.arange(int(seconds * RATE)) / RATE
    vibrato = 1 + 0.002 * np.sin(2 * np.pi * 4.5 * t)
    tone = np.sin(2 * np.pi * freq * vibrato * t) + 0.25 * np.sin(4 * np.pi * freq * t)
    attack = np.minimum(t / 1.8, 1)
    release = np.minimum((seconds - t) / 2.2, 1)
    return tone * attack * release


def music(seconds: float, path: Path) -> None:
    """Acordes ambientales (Cmaj9 – Am9 – Fmaj9 – G6) que se superponen suavemente."""
    chords = [[130.81, 196.00, 246.94, 293.66, 329.63],   # Cmaj9
              [110.00, 164.81, 196.00, 246.94, 261.63],   # Am9
              [87.31, 174.61, 220.00, 261.63, 329.63],    # Fmaj9
              [98.00, 196.00, 246.94, 293.66, 329.63]]    # G6
    step, length = 6.0, 8.5  # cada acorde dura 8.5 s y empieza 6 s después del anterior
    total = np.zeros(int((seconds + length) * RATE))
    i = 0
    while i * step < seconds:
        chord = sum(note(f, length) for f in chords[i % len(chords)])
        a = int(i * step * RATE)
        total[a:a + len(chord)] += chord
        i += 1
    total = total[: int(seconds * RATE)]
    # Eco suave para darle espacio
    for delay, gain in ((0.23, 0.35), (0.47, 0.2)):
        d = int(delay * RATE)
        total[d:] += gain * total[:-d]
    fade = int(3 * RATE)
    total[:fade] *= np.linspace(0, 1, fade)
    total[-fade:] *= np.linspace(1, 0, fade)
    total = total / np.abs(total).max() * 0.25  # volumen bajo, de fondo
    stereo = np.stack([total, np.roll(total, int(0.012 * RATE))], axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())


def main(folder: Path) -> Path:
    info = json.loads((folder / "esperas.json").read_text())
    video = folder / info["video"]
    parts = segments(duration_of(video), info["waits"])
    silent = folder / "sin_audio.mp4"
    speed_up(video, parts, silent)
    seconds = duration_of(silent)
    track = folder / "musica.wav"
    music(seconds, track)
    final = folder / "asesoria-demo.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(track),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(final)], check=True)
    fast = sum(e - s for s, e, f in parts if f)
    print(f"{final} · {seconds:.0f} s (se aceleraron {fast:.0f} s de espera)")
    return final


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    main(parser.parse_args().folder)
