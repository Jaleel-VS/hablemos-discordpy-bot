"""Multi-message conversation-style quote image generator."""
import logging
from html import escape
from os import path

import imgkit

from cogs.quote_generator_cog.emoji import visual_length

logger = logging.getLogger(__name__)

dir_path = path.dirname(path.realpath(__file__))


def _compute_font_size(total_length: int) -> int:
    if total_length <= 100:
        return 22
    if total_length <= 200:
        return 19
    if total_length <= 350:
        return 16
    return 14


def create_multi_image(
    messages: list[tuple[str, str, str]],
    *,
    output_path: str | None = None,
) -> str:
    """Generate a conversation-style quote image.

    Parameters
    ----------
    messages:
        List of (username, avatar_url, content) tuples, oldest first.
    output_path:
        Optional output file path.

    Returns the output file path.
    """
    total_length = sum(visual_length(c) for _, _, c in messages)
    font_px = _compute_font_size(total_length)

    rows_html = ""
    for username, avatar_url, content in messages:
        safe_name = escape(username)
        rows_html += f'''
        <div class="msg-row">
          <img class="avatar" src="{avatar_url}" />
          <div class="bubble">
            <span class="name">{safe_name}</span>
            <span class="text">{content}</span>
          </div>
        </div>'''

    options = {
        'format': 'png',
        'encoding': 'UTF-8',
        'enable-local-file-access': None,
        'crop-w': '640',
    }

    html = f'''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <style>
    @font-face {{
      font-family: 'Helvetica Neue';
      src: url('{dir_path}/fonts/HelveticaNeue-Roman.eot');
      src: url('{dir_path}/fonts/HelveticaNeue-Roman.eot?#iefix') format('embedded-opentype'),
           url('{dir_path}/fonts/HelveticaNeue-Roman.woff') format('woff'),
           url('{dir_path}/fonts/HelveticaNeue-Roman.ttf') format('truetype');
      font-weight: normal;
      font-style: normal;
      font-display: swap;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ background: transparent; }}
    body {{ font-family: 'Helvetica Neue', system-ui, sans-serif; }}

    .card {{
      width: 620px;
      background: #2b2d31;
      border-radius: 12px;
      padding: 20px 16px;
      margin: 10px;
    }}

    .msg-row {{
      display: flex;
      align-items: flex-start;
      gap: 12px;
      padding: 10px 0;
    }}

    .msg-row + .msg-row {{
      border-top: 1px solid rgba(255,255,255,0.06);
    }}

    .avatar {{
      width: 40px;
      height: 40px;
      border-radius: 50%;
      flex-shrink: 0;
    }}

    .bubble {{
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }}

    .name {{
      font-size: 14px;
      font-weight: 700;
      color: #f2f3f5;
    }}

    .text {{
      font-size: {font_px}px;
      color: #dbdee1;
      line-height: 1.4;
      word-wrap: break-word;
    }}
  </style>
</head>
<body>
  <div class="card">
    {rows_html}
  </div>
</body>
</html>
    '''

    img_path = output_path or f"{dir_path}/picture_multi.png"
    imgkit.from_string(html, img_path, options=options)
    return img_path
