"""Configuration for the tasks cog."""
from config import get_int_env

TASKS_CHANNEL_ID = get_int_env("TASKS_CHANNEL_ID", "1437832952028467251")
TASKS_CATEGORY_ID = get_int_env("TASKS_CATEGORY_ID", "1003424008907272314")

ASSIGNABLE_MEMBER_IDS = [
    354352443502493706,
    146726561981136897,
    216848576549093376,
]

STATUSES = {
    "todo": ("📋", "Todo", 0x95A5A6),
    "in_progress": ("🔨", "In Progress", 0xF1C40F),
    "done": ("✅", "Done", 0x2ECC71),
}

STATUS_CHOICES = [(f"{emoji} {label}", key) for key, (emoji, label, _) in STATUSES.items()]
