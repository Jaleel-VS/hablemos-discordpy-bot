"""Polaroid-style quote image generator."""
import logging
from html import escape
from os import path

import imgkit

from cogs.quote_generator_cog.emoji import visual_length

logger = logging.getLogger(__name__)

dir_path = path.dirname(path.realpath(__file__))


def _compute_font_size(message: str) -> int:
    length = visual_length(message or "")
    if length <= 40:
        return 32
    if length <= 80:
        return 26
    if length <= 130:
        return 22
    return 18


def create_image3(user_name: str, user_avatar: str, message_content: str, *, output_path: str | None = None) -> str:
    """Generate a polaroid-style quote image. Returns the output file path."""
    options = {
        'format': 'png',
        'encoding': 'UTF-8',
        'enable-local-file-access': None,
        'width': '580',
        'transparent': '',
    }

    font_px = _compute_font_size(message_content)
    safe_name = escape(user_name)

    html = f'''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <style>
    @font-face {{
      font-family: 'Calligraffiti';
      src: url('{dir_path}/fonts/Calligraffiti-webfont.ttf') format('truetype');
      font-weight: normal;
      font-style: normal;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ background: transparent; width: 580px; }}

    .polaroid {{
      width: 480px;
      margin: 40px auto;
      background: #fafaf7;
      padding: 20px 20px 0;
      box-shadow: 4px 6px 18px rgba(0,0,0,0.45);
      transform: rotate(-1.5deg);
    }}

    .photo {{
      width: 440px;
      height: 400px;
      background: url('{user_avatar}') center/cover no-repeat;
      display: block;
      -webkit-filter: sepia(0.25) saturate(0.85) contrast(1.05) brightness(1.05);
      filter: sepia(0.25) saturate(0.85) contrast(1.05) brightness(1.05);
    }}

    .caption {{
      font-family: 'Calligraffiti', cursive;
      font-size: {font_px}px;
      color: #222;
      text-align: center;
      padding: 18px 10px 14px;
      line-height: 1.3;
      min-height: 80px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }}

    .caption .text {{
      margin-bottom: 6px;
    }}

    .caption .author {{
      font-size: {max(14, font_px - 6)}px;
      color: #666;
    }}
  </style>
</head>
<body>
  <div class="polaroid">
    <div class="photo"></div>
    <div class="caption">
      <div class="text">{message_content}</div>
      <div class="author">— {safe_name}</div>
    </div>
  </div>
</body>
</html>
    '''

    img_path = output_path or f"{dir_path}/picture3.png"
    imgkit.from_string(html, img_path, options=options)
    return img_path


if __name__ == "__main__":
    create_image3(
        'Priúñaku',
        'https://tse1.mm.bing.net/th/id/OIP.aQvztH3rNT-QMNNeixa91QHaNK?rs=1&pid=ImgDetMain&o=7&rm=3',
        'Dolor sit amet',
    )
