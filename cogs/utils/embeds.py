"""Shared embed helper functions."""
from discord import Embed, Color


def green_embed(text: str) -> Embed:
    return Embed(description=text, color=Color(0x00FF00))


def red_embed(text: str) -> Embed:
    return Embed(description=text, color=Color(0xE74C3C))


def blue_embed(text: str) -> Embed:
    return Embed(description=text, color=Color(0x3498DB))


def yellow_embed(text: str) -> Embed:
    return Embed(description=text, color=Color(0xF1C40F))
