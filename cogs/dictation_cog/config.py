"""Dictation cog configuration."""

from config import get_int_env, get_str_env

S3_BUCKET = get_str_env("DICTATION_S3_BUCKET", "hablemos-dictation-195950944512")
S3_REGION = get_str_env("DICTATION_S3_REGION", "us-east-1")
ANSWER_TIMEOUT_SECONDS = get_int_env("DICTATION_ANSWER_TIMEOUT", 120)
MAX_SCORE = 4
