from os import path
import imgkit


dir_path = path.dirname(path.realpath(__file__))


def _compute_phrase_font_size(message: str) -> int:
    length = len(message or "")
    if length <= 60:
        return 38
    if length <= 90:
        return 32
    if length <= 130:
        return 30
    if length <= 180:
        return 28
    return 24


def _compute_quote_glyph_font_size(message: str) -> int:
    length = len(message or "")
    if length <= 60:
        return 116
    if length <= 90:
        return 102
    if length <= 130:
        return 90
    if length <= 180:
        return 78
    return 70


def create_image2(user_name: str, user_avatar: str, message_content: str) -> str:
    options = {
        'format': 'png',
        'encoding': 'UTF-8',
        'enable-local-file-access': None,
        'crop-w': '640',
        'crop-h': '640',
    }

    phrase_font_px = _compute_phrase_font_size(message_content)
    quote_glyph_font_px = _compute_quote_glyph_font_size(message_content)

    # Use the user's avatar as the background image for the variant
    background_image_url = user_avatar

    html = f'''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <style>
    @font-face {{
      font-family: 'Gothic CG No1';
      src: url('{dir_path}/fonts/Gothic CG No1 Regular.otf') format('opentype');
      font-weight: 400;
      font-style: normal;
      font-display: swap;
    }}

    :root {{ --fg: #fff; --bg: #000; }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; background: transparent; }}

    body {{ font-family: 'Gothic CG No1', system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}

    .quote-card {{
      position: relative;
      width: 640px;
      height: 640px;
      margin: 0;
      color: var(--fg);
      background: url('{background_image_url}') center/cover no-repeat;
      overflow: hidden;
    }}

    /* subtle full-image gray tint to help against bright images */
    .base-tint {{
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0,0,0,0.12);
      z-index: 0;
      pointer-events: none;
    }}

    /* explicit gradient overlay for better wkhtmltoimage compatibility */
    .overlay {{
      position: absolute;
      top: 0; left: 0; right: 0; bottom: 0;
      /* darker blend to compensate for base tint */
      background: -webkit-linear-gradient(top,
        rgba(0,0,0,0) 52%,
        rgba(0,0,0,0.50) 72%,
        rgba(0,0,0,0.75) 86%,
        rgba(0,0,0,0.88) 100%
      );
      background: linear-gradient(to bottom,
        rgba(0,0,0,0) 52%,
        rgba(0,0,0,0.50) 72%,
        rgba(0,0,0,0.75) 86%,
        rgba(0,0,0,0.88) 100%
      );
      z-index: 0;
      pointer-events: none;
    }}

    .content {{
      position: absolute;
      left: 50%; top: 63%;
      transform: translate(-50%, -50%);
      text-align: center;
      width: 90%;
      padding: 0 16px;
      z-index: 1;
    }}

    .quote-container {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.25em;
      margin-bottom: 0.1rem;
    }}

    .left-quote, .right-quote {{
      font-size: {quote_glyph_font_px}px;
      font-weight: 800;
      line-height: 1;
      letter-spacing: .12em;
      color: #fff;
      /* outline for better legibility on busy backgrounds */
      -webkit-text-stroke: {max(2, min(8, int((_compute_quote_glyph_font_size.__code__.co_consts and 0) or 0) or 0))}px rgba(0,0,0,0.85);
    }}

    .phrase {{
      margin: 0;
      font-size: {phrase_font_px}px;
      font-weight: 700;
      line-height: 1.35;
      text-transform: uppercase;
    }}

    .rule {{
      display: inline-block;
      width: 25%;
      height: 2px;
      background: var(--fg);
      opacity: .95;
      margin: 1.1rem 0 .8rem;
    }}

    .author {{
      font-weight: 800;
      letter-spacing: .15em;
      text-transform: uppercase;
      font-size: 22px;
    }}
  </style>
  <meta name="viewport" content="width=640, initial-scale=1" />
  <title>Quote Card</title>
  </head>
  <body>
    <div class="quote-card">
      <div class="base-tint"></div>
      <div class="overlay"></div>
      <div class="content">
        <div class="quote-container" aria-hidden="true">
          <div class="left-quote">“</div>
          <div class="right-quote">”</div>
        </div>
        <p class="phrase">{message_content}</p>
        <span class="rule" aria-hidden="true"></span>
        <div class="author">{user_name}</div>
      </div>
    </div>
  </body>
  </html>
    '''

    img_path = f"{dir_path}/picture2.png"
    imgkit.from_string(html, img_path, options=options)
    return img_path


if __name__ == "__main__":
    create_image2(
        'Priúñaku',
        'https://tse1.mm.bing.net/th/id/OIP.aQvztH3rNT-QMNNeixa91QHaNK?rs=1&pid=ImgDetMain&o=7&rm=3',
        'Dolor sit amet',
    )


