"Generate the animation of throwing tomatoes."
from pathlib import Path
from PIL import Image, ImageSequence

BASE_DIR = Path(__file__).resolve().parent
TOMATOES_OVERLAY = Image.open(BASE_DIR / "overlay.webp")

def generate_tomatoes(background: Image.Image, output_path: str | None = None) -> str:
    output_path = output_path or str(BASE_DIR / "output.webp")
    durations = []
    frames = []

    for frame in ImageSequence.Iterator(TOMATOES_OVERLAY):
        frame = frame.convert("RGBA")
        result = frame.copy()
        resized_bg = background.resize(frame.size)
        combined = Image.alpha_composite(resized_bg, result)

        frames.append(combined)
        durations.append(frame.info.get("duration", 100))

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        disposal=2,
        transparency=0
    )

    return output_path
