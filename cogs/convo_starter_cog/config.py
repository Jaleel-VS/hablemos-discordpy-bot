"""Configuration for the Conversation Starter cog."""
import os

# Channels where Spanish is shown first (Spanish-English channels)
SPA_CHANNELS = [
    int(x) for x in os.getenv(
        'CONVO_SPA_CHANNELS',
        '809349064029241344,243858509123289089,388539967053496322,477630693292113932'
    ).split(',')
]
