"""
Leaderboard image generation using Pillow (PIL)
Pure Python implementation - no external dependencies like wkhtmltopdf
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO
import requests
from pathlib import Path
from datetime import datetime

# Get directory for font files
FONT_DIR = Path(__file__).parent / "fonts"


def download_avatar(url: str, size: int = 64) -> Image.Image:
    """Download and process user avatar"""
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()

        avatar = Image.open(BytesIO(response.content))
        avatar = avatar.convert('RGBA')
        avatar = avatar.resize((size, size), Image.Resampling.LANCZOS)

        # Create circular mask
        mask = Image.new('L', (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, size, size), fill=255)

        # Apply mask
        output = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        output.paste(avatar, (0, 0))
        output.putalpha(mask)

        return output
    except Exception:
        # Return default avatar on error
        return create_default_avatar(size)


def create_default_avatar(size: int = 64) -> Image.Image:
    """Create a default avatar (simple circle)"""
    avatar = Image.new('RGBA', (size, size), (114, 137, 218, 255))  # Discord blurple

    # Draw a simple user icon
    draw = ImageDraw.Draw(avatar)
    # Head circle
    head_size = size // 3
    head_pos = (size // 2 - head_size // 2, size // 3 - head_size // 2)
    draw.ellipse(
        (head_pos[0], head_pos[1], head_pos[0] + head_size, head_pos[1] + head_size),
        fill=(255, 255, 255, 255)
    )
    # Body arc
    body_width = int(size * 0.6)
    body_height = int(size * 0.4)
    body_pos = (size // 2 - body_width // 2, size - body_height)
    draw.ellipse(
        (body_pos[0], body_pos[1], body_pos[0] + body_width, body_pos[1] + body_height * 2),
        fill=(255, 255, 255, 255)
    )

    # Create circular mask
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)
    avatar.putalpha(mask)

    return avatar


def get_font(size: int, bold: bool = False):
    """Load font with fallback to default"""
    try:
        if bold:
            font_path = FONT_DIR / "HelveticaNeue-Bold.ttf"
            if not font_path.exists():
                font_path = FONT_DIR / "HelveticaNeue-Roman.ttf"
        else:
            font_path = FONT_DIR / "HelveticaNeue-Roman.ttf"

        if font_path.exists():
            return ImageFont.truetype(str(font_path), size)
    except Exception:
        pass

    # Fallback to default font
    return ImageFont.load_default()


def draw_gradient_rect(draw, bbox, color1, color2):
    """Draw a vertical gradient rectangle"""
    x0, y0, x1, y1 = bbox
    height = y1 - y0

    for i in range(height):
        ratio = i / height
        r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
        g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
        b = int(color1[2] * (1 - ratio) + color2[2] * ratio)

        draw.rectangle(
            [(x0, y0 + i), (x1, y0 + i + 1)],
            fill=(r, g, b)
        )


def get_rank_colors(rank: int) -> tuple:
    """Get background gradient colors for rank"""
    if rank == 1:
        # Gold gradient
        return ((255, 215, 0), (255, 165, 0))
    elif rank == 2:
        # Silver gradient
        return ((232, 232, 232), (192, 192, 192))
    elif rank == 3:
        # Bronze gradient
        return ((244, 164, 96), (205, 127, 50))
    elif rank <= 10:
        # Purple gradient (darkened for WCAG AA compliance)
        return ((88, 101, 191), (118, 75, 162))
    else:
        # Dark blue gradient (darkened for WCAG AA compliance)
        return ((45, 105, 196), (37, 99, 235))


def get_text_color(rank: int) -> tuple:
    """Get text color based on rank"""
    if rank <= 3:
        return (0, 0, 0)  # Black for medal ranks
    else:
        return (255, 255, 255)  # White for others


def get_rank_emoji(rank: int) -> str:
    """Get rank number"""
    return f"#{rank}"


def draw_star(draw: ImageDraw.ImageDraw, center: tuple[int, int], size: int, color: tuple, outline_color: tuple = None):
    """Draw a 5-pointed star at the given center position"""
    import math
    cx, cy = center
    points = []
    for i in range(10):
        # Alternate between outer and inner radius
        radius = size if i % 2 == 0 else size * 0.4
        # Start from top (-90 degrees) and go clockwise
        angle = math.radians(-90 + i * 36)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        points.append((x, y))

    draw.polygon(points, fill=color, outline=outline_color)


def generate_leaderboard_image(
    leaderboard_data: list[dict],
    board_type: str,
    round_info: dict
) -> str:
    """
    Generate leaderboard image using Pillow.

    Args:
        leaderboard_data: List of dicts with keys:
            - rank (int)
            - user_id (int)
            - username (str)
            - total_score (int)
            - active_days (int)
            - avatar_url (str)
            - is_previous_winner (bool)

        board_type: 'spanish' | 'english' | 'combined'

        round_info: Dict with keys:
            - round_number (int)
            - end_date (datetime)

    Returns:
        str: Path to generated PNG file
    """
    # Image dimensions
    WIDTH = 800
    ENTRY_HEIGHT = 80
    PADDING = 20
    HEIGHT = PADDING + (len(leaderboard_data) * ENTRY_HEIGHT) + PADDING

    # Create image with dark background
    image = Image.new('RGB', (WIDTH, HEIGHT), color=(26, 27, 30))
    draw = ImageDraw.Draw(image)

    # Load fonts
    username_font = get_font(24, bold=False)
    score_font = get_font(20, bold=True)
    rank_font = get_font(28, bold=True)

    # Draw entries
    y_offset = PADDING

    for entry in leaderboard_data:
        rank = entry['rank']
        username = entry['username']
        total_score = entry['total_score']
        avatar_url = entry['avatar_url']
        is_winner = entry['is_previous_winner']

        # Get colors for this rank
        bg_color1, bg_color2 = get_rank_colors(rank)
        text_color = get_text_color(rank)

        # Entry dimensions
        entry_width = WIDTH - 2 * PADDING
        entry_height = ENTRY_HEIGHT - 10

        # Create gradient rectangle
        gradient_img = Image.new('RGB', (entry_width, entry_height), (0, 0, 0))
        gradient_draw = ImageDraw.Draw(gradient_img)
        draw_gradient_rect(
            gradient_draw,
            (0, 0, entry_width, entry_height),
            bg_color1,
            bg_color2
        )

        # Create rounded rectangle mask
        mask = Image.new('L', (entry_width, entry_height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle(
            (0, 0, entry_width, entry_height),
            radius=12,
            fill=255
        )

        # Paste gradient with rounded corners onto main image
        image.paste(gradient_img, (PADDING, y_offset), mask)

        # Draw rank badge
        rank_text = get_rank_emoji(rank)
        rank_bbox = draw.textbbox((0, 0), rank_text, font=rank_font)
        rank_x = PADDING + 20
        rank_y = y_offset + (ENTRY_HEIGHT - 10) // 2 - (rank_bbox[3] - rank_bbox[1]) // 2
        draw.text((rank_x, rank_y), rank_text, fill=text_color, font=rank_font)

        # Download and draw avatar (use fixed offset for consistent alignment)
        avatar_size = 56
        avatar = download_avatar(avatar_url, avatar_size)
        RANK_AREA_WIDTH = 60  # Fixed width for rank area
        avatar_x = PADDING + 20 + RANK_AREA_WIDTH
        avatar_y = y_offset + (ENTRY_HEIGHT - 10) // 2 - avatar_size // 2

        # Add border to avatar
        border_size = 3
        border_avatar = Image.new('RGBA', (avatar_size + border_size * 2, avatar_size + border_size * 2), (255, 255, 255, 100))
        border_mask = Image.new('L', (avatar_size + border_size * 2, avatar_size + border_size * 2), 0)
        border_draw = ImageDraw.Draw(border_mask)
        border_draw.ellipse((0, 0, avatar_size + border_size * 2, avatar_size + border_size * 2), fill=255)
        border_avatar.putalpha(border_mask)

        image.paste(border_avatar, (avatar_x - border_size, avatar_y - border_size), border_avatar)
        image.paste(avatar, (avatar_x, avatar_y), avatar)

        # Calculate username position
        username_x = avatar_x + avatar_size + 20
        username_bbox = draw.textbbox((0, 0), username, font=username_font)
        username_y = y_offset + (ENTRY_HEIGHT - 10) // 2 - (username_bbox[3] - username_bbox[1]) // 2

        # Draw star icon if previous winner
        if is_winner:
            star_size = 10
            star_x = username_x + star_size
            star_y = username_y + (username_bbox[3] - username_bbox[1]) // 2
            # Gold star with darker outline
            draw_star(draw, (star_x, star_y), star_size, color=(255, 215, 0), outline_color=(200, 160, 0))
            username_x += star_size * 2 + 8  # Offset username after star

        # Truncate username if too long
        username_text = username
        max_username_width = 380 if is_winner else 400  # Slightly less width if star is shown
        if draw.textlength(username_text, font=username_font) > max_username_width:
            while draw.textlength(username_text + "...", font=username_font) > max_username_width and len(username_text) > 10:
                username_text = username_text[:-1]
            username_text += "..."

        draw.text((username_x, username_y), username_text, fill=text_color, font=username_font)

        # Draw score (right-aligned)
        score_text = f"{total_score} pts"
        score_bbox = draw.textbbox((0, 0), score_text, font=score_font)
        score_width = score_bbox[2] - score_bbox[0]
        score_x = WIDTH - PADDING - score_width - 20
        score_y = y_offset + (ENTRY_HEIGHT - 10) // 2 - (score_bbox[3] - score_bbox[1]) // 2
        draw.text((score_x, score_y), score_text, fill=text_color, font=score_font)

        y_offset += ENTRY_HEIGHT

    # Save image
    output_path = Path(__file__).parent / f"leaderboard_{board_type}_{round_info['round_number']}.png"
    image.save(output_path, 'PNG', quality=95)

    return str(output_path)


if __name__ == "__main__":
    # Test with sample data
    sample_data = [
        {
            'rank': 1,
            'user_id': 12345,
            'username': 'TopPlayer',
            'total_score': 500,
            'active_days': 14,
            'avatar_url': 'https://cdn.discordapp.com/embed/avatars/0.png',
            'is_previous_winner': True
        },
        {
            'rank': 2,
            'user_id': 23456,
            'username': 'SecondPlace',
            'total_score': 450,
            'active_days': 12,
            'avatar_url': 'https://cdn.discordapp.com/embed/avatars/1.png',
            'is_previous_winner': False
        },
        {
            'rank': 3,
            'user_id': 34567,
            'username': 'ThirdPlace',
            'total_score': 400,
            'active_days': 11,
            'avatar_url': 'https://cdn.discordapp.com/embed/avatars/2.png',
            'is_previous_winner': False
        },
    ]

    round_info = {
        'round_number': 5,
        'end_date': datetime.now()
    }

    img_path = generate_leaderboard_image(sample_data, 'combined', round_info)
    print(f"Generated image: {img_path}")
