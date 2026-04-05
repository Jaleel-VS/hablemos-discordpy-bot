"""Higher-or-Lower dataset — curated Google search volumes (monthly, global)."""
import random

# (term, monthly_search_volume)
# Source: Ahrefs Top Google Searches, January 2026
TERMS: list[tuple[str, int]] = [
    # Mega tier (100M+)
    ("ChatGPT", 768_300_000),
    ("WhatsApp Web", 533_400_000),
    ("YouTube", 390_800_000),
    ("Translate", 254_300_000),
    ("Facebook", 207_200_000),
    ("Amazon", 204_100_000),
    ("Google", 192_300_000),
    ("Gmail", 189_800_000),
    ("Canva", 185_000_000),
    ("Instagram", 159_100_000),
    ("Weather", 156_300_000),
    ("Google Translate", 107_400_000),
    ("WhatsApp", 103_500_000),
    # High tier (25M-100M)
    ("Roblox", 98_400_000),
    ("TikTok", 81_200_000),
    ("Wordle", 74_100_000),
    ("Pinterest", 68_800_000),
    ("Netflix", 62_300_000),
    ("Google Maps", 59_200_000),
    ("Speed Test", 52_700_000),
    ("Yahoo", 51_300_000),
    ("Real Madrid", 50_300_000),
    ("Outlook", 49_200_000),
    ("LinkedIn", 45_600_000),
    ("Yahoo Mail", 44_500_000),
    ("Twitter", 42_600_000),
    ("Spotify", 41_300_000),
    ("Discord", 39_300_000),
    ("Shein", 38_700_000),
    ("NBA", 37_200_000),
    ("Calculator", 34_800_000),
    ("Gemini", 34_200_000),
    ("eBay", 33_100_000),
    ("NFL", 33_000_000),
    ("BBC News", 32_500_000),
    ("Premier League", 29_400_000),
    ("IKEA", 28_800_000),
    ("Walmart", 28_500_000),
    ("Kahoot", 28_400_000),
    ("Google Docs", 27_500_000),
    ("Temu", 27_400_000),
    ("Google Classroom", 26_300_000),
    ("Amazon Prime", 26_100_000),
    ("DeepSeek", 25_000_000),
    # Mid tier (10M-25M)
    ("Airbnb", 24_000_000),
    ("Reddit", 22_000_000),
    ("Costco", 20_000_000),
    ("Fox News", 20_680_000),
    ("Home Depot", 16_680_000),
    ("Target", 17_460_000),
    ("Etsy", 15_000_000),
    ("Solitaire", 14_000_000),
    ("ESPN", 13_000_000),
    ("NBA Scores", 12_000_000),
    ("Zillow", 10_940_000),
    ("Cool Math Games", 10_520_000),
    ("Food Near Me", 10_410_000),
    # Lower tier (3M-10M)
    ("CNN", 7_010_000),
    ("Best Buy", 6_990_000),
    ("Lululemon", 6_560_000),
    ("PayPal", 5_890_000),
    ("Tesla Stock", 7_170_000),
    ("Capital One", 7_180_000),
    ("Apple", 4_950_000),
    ("Macy's", 4_860_000),
    ("CVS", 5_730_000),
    ("Walgreens", 5_150_000),
    ("FedEx Tracking", 5_990_000),
    ("USPS Tracking", 10_980_000),
    ("Google Flights", 12_420_000),
    ("Google Drive", 7_010_000),
    ("Google Slides", 5_410_000),
    ("Internet Speed Test", 5_120_000),
    ("Nvidia Stock", 5_050_000),
    ("MLB", 5_250_000),
    ("Dow Jones", 10_570_000),
    ("Restaurants Near Me", 6_440_000),
    ("Facebook Marketplace", 5_560_000),
    ("Snake Game", 5_610_000),
]


def pick_pair(exclude: set[str] | None = None) -> tuple[str, int, str, int]:
    """Pick two distinct terms, avoiding any in *exclude*.

    Returns (known_term, known_volume, mystery_term, mystery_volume).
    """
    pool = [t for t in TERMS if not exclude or t[0] not in exclude]
    a, b = random.sample(pool, 2)
    return a[0], a[1], b[0], b[1]
