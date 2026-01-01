from os import path
import imgkit
from datetime import datetime

dir_path = path.dirname(path.realpath(__file__))


def _get_rank_display(rank: int) -> str:
    """Returns medal emoji for top 3, otherwise #rank format"""
    if rank == 1:
        return "🥇"
    elif rank == 2:
        return "🥈"
    elif rank == 3:
        return "🥉"
    else:
        return f"#{rank}"


def _get_board_emoji(board_type: str) -> str:
    """Returns emoji for board type"""
    if board_type == 'spanish':
        return "🇪🇸"
    elif board_type == 'english':
        return "🇬🇧"
    else:  # combined
        return "🌍"


def _get_board_title(board_type: str) -> str:
    """Returns title for board type"""
    if board_type == 'spanish':
        return "Spanish League"
    elif board_type == 'english':
        return "English League"
    else:  # combined
        return "Combined League"


def _format_username(username: str, is_winner: bool) -> str:
    """Formats username with star indicator if previous winner, truncates if needed"""
    # Truncate username if too long
    if len(username) > 20:
        username = username[:17] + "..."

    # Add star for previous winners
    if is_winner:
        return f"⭐ {username}"
    return username


def _get_entry_class(rank: int, is_requester: bool = False) -> str:
    """Returns CSS class name for entry based on rank"""
    if is_requester:
        return "entry requester-entry"
    elif rank == 1:
        return "entry rank-1"
    elif rank == 2:
        return "entry rank-2"
    elif rank == 3:
        return "entry rank-3"
    elif rank <= 10:
        return "entry rank-4-10"
    else:
        # Alternate colors for ranks 11+
        if rank % 2 == 1:
            return "entry rank-11-plus rank-odd"
        else:
            return "entry rank-11-plus rank-even"


def _calculate_image_height(num_entries: int) -> int:
    """Calculate dynamic height for the image"""
    # No header needed - title/round info moved to Discord embed
    padding_height = 40  # Top and bottom padding

    # Increased height per entry for bigger fonts/avatars
    # Top 3 get more height due to larger styling
    entry_heights = sum([85 if i < 3 else 75 for i in range(num_entries)])

    total_height = padding_height + entry_heights
    return max(400, min(2400, total_height))  # Clamp between 400-2400


def _generate_html(
    leaderboard_data: list[dict],
    board_type: str,
    round_info: dict
) -> tuple[str, int]:
    """Generate HTML string for leaderboard"""

    board_emoji = _get_board_emoji(board_type)
    board_title = _get_board_title(board_type)
    round_number = round_info['round_number']
    end_date = round_info['end_date']

    # Format end date
    if isinstance(end_date, datetime):
        end_date_str = end_date.strftime('%Y-%m-%d %H:%M UTC')
    else:
        end_date_str = str(end_date)

    # Calculate image height
    image_height = _calculate_image_height(len(leaderboard_data))

    # Build entries HTML
    entries_html = ""
    for entry in leaderboard_data:
        rank = entry['rank']
        username = entry['username']
        total_score = entry['total_score']
        avatar_url = entry['avatar_url']
        is_winner = entry['is_previous_winner']

        rank_display = _get_rank_display(rank)
        formatted_username = _format_username(username, is_winner)
        entry_class = _get_entry_class(rank)

        entries_html += f'''
        <div class="{entry_class}">
            <div class="rank-badge">{rank_display}</div>
            <img src="{avatar_url}" class="avatar" alt="avatar" />
            <div class="username">{formatted_username}</div>
            <div class="stats">
                <div class="score">{total_score} pts</div>
            </div>
        </div>
        '''

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

        @font-face {{
            font-family: 'HelveticaNeue';
            src: url('{dir_path}/fonts/HelveticaNeue-Roman.ttf') format('truetype');
            font-weight: 400;
            font-style: normal;
            font-display: swap;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        html, body {{
            margin: 0;
            padding: 0;
            background: transparent;
        }}

        body {{
            font-family: 'HelveticaNeue', 'Helvetica Neue', Helvetica, Arial, sans-serif;
            color: #ffffff;
        }}

        .leaderboard-container {{
            width: 800px;
            background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
            padding: 20px 30px;
        }}

        .entries {{
            margin: 0;
        }}

        .entry {{
            display: flex;
            align-items: center;
            padding: 18px 25px;
            margin-bottom: 12px;
            border-radius: 12px;
            transition: transform 0.2s;
        }}

        /* Rank 1 - Gold */
        .entry.rank-1 {{
            background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
            border: 3px solid #FFD700;
            box-shadow: 0 4px 12px rgba(255, 215, 0, 0.4);
            padding: 22px 25px;
            color: #000000;
        }}

        .entry.rank-1 .username,
        .entry.rank-1 .rank-badge {{
            font-weight: bold;
            color: #000000;
        }}

        .entry.rank-1 .stats {{
            color: #000000;
        }}

        /* Rank 2 - Silver */
        .entry.rank-2 {{
            background: linear-gradient(135deg, #E8E8E8 0%, #C0C0C0 100%);
            border: 3px solid #C0C0C0;
            box-shadow: 0 4px 12px rgba(192, 192, 192, 0.4);
            padding: 22px 25px;
            color: #000000;
        }}

        .entry.rank-2 .username,
        .entry.rank-2 .rank-badge {{
            font-weight: bold;
            color: #000000;
        }}

        .entry.rank-2 .stats {{
            color: #000000;
        }}

        /* Rank 3 - Bronze */
        .entry.rank-3 {{
            background: linear-gradient(135deg, #F4A460 0%, #CD7F32 100%);
            border: 3px solid #CD7F32;
            box-shadow: 0 4px 12px rgba(205, 127, 50, 0.4);
            padding: 22px 25px;
            color: #000000;
        }}

        .entry.rank-3 .username,
        .entry.rank-3 .rank-badge {{
            font-weight: bold;
            color: #000000;
        }}

        .entry.rank-3 .stats {{
            color: #000000;
        }}

        /* Ranks 4-10 - Purple gradient */
        .entry.rank-4-10 {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border: 2px solid #667eea;
            box-shadow: 0 3px 8px rgba(102, 126, 234, 0.3);
        }}

        /* Ranks 11+ - Alternating subtle colors */
        .entry.rank-11-plus {{
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}

        .entry.rank-odd {{
            background: rgba(59, 130, 246, 0.2);
        }}

        .entry.rank-even {{
            background: rgba(99, 102, 241, 0.2);
        }}

        .rank-badge {{
            min-width: 80px;
            text-align: center;
            font-weight: bold;
            font-size: 30px;
        }}

        .avatar {{
            width: 64px;
            height: 64px;
            border-radius: 50%;
            margin: 0 20px;
            border: 3px solid rgba(255, 255, 255, 0.3);
        }}

        .username {{
            font-size: 27px;
            font-weight: 500;
            flex: 1;
            max-width: 400px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        .stats {{
            text-align: right;
            margin-left: auto;
        }}

        .score {{
            font-size: 24px;
            font-weight: 600;
        }}
    </style>
    <meta name="viewport" content="width=800, initial-scale=1" />
    <title>League Leaderboard</title>
</head>
<body>
    <div class="leaderboard-container">
        <div class="entries">
            {entries_html}
        </div>
    </div>
</body>
</html>
    '''

    return html, image_height


def generate_leaderboard_image(
    leaderboard_data: list[dict],
    board_type: str,
    round_info: dict
) -> str:
    """
    Generate leaderboard image using HTML/CSS and imgkit.

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
    # Generate HTML
    html, image_height = _generate_html(leaderboard_data, board_type, round_info)

    # Configure imgkit options
    options = {
        'format': 'png',
        'encoding': 'UTF-8',
        'enable-local-file-access': None,
        'crop-w': '800',
        'crop-h': str(image_height),
        'quality': '100',
    }

    # Generate image
    img_path = f"{dir_path}/leaderboard_{board_type}_{round_info['round_number']}.png"
    imgkit.from_string(html, img_path, options=options)

    return img_path


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
