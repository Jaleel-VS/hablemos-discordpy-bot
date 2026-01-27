# Changelog

A comprehensive changelog for **Hablemos** - a Spanish-English language learning Discord bot.

---

## [Unreleased] - Current

### Exchange Request System
- **feat:** Add exchange request cog for language partner matching (`5322567`)
- **feat:** Improve exchange request form UX with better flow (`b0daf1e`)
- **feat:** Add profile button and clearer contact preference options (`af32ab3`)
- **feat:** Add column layout and country preference field (`c643a8c`)
- **refactor:** Simplify exchange request embed display (`abc8609`)
- **fix:** Remove section headers to reduce vertical spacing (`64f67ce`)
- **fix:** Shorten modal label and remove delete button (`4a0eec5`)

### Website Manager
- **feat:** Add website manager cog for podcast/resource management (`1993206`)

---

## Language League System

A comprehensive competitive leaderboard system with biweekly rounds.

### Core Implementation
- **feat:** Add Language League Cog with leaderboard functionality and database integration (`e5f39e6`)
- **feat:** Implement biweekly league rounds with winner announcements and database updates (`9327ab9`)
- **feat:** Add leaderboard image generation and user enrichment for league rankings (`2db8e90`)

### Leaderboard Improvements
- **fix:** Update leaderboard image generation to display top 10 users instead of top 20 (`90f3860`)
- **fix:** Update font file extension from .otf to .ttf in leaderboard image generation (`afeceaa`)
- **update:** Leaderboard image styling improvements (`3a6e2e4`)
- **update:** Leaderboard logic refinements (`a55f351`)
- **update:** Switch leaderboard image to use Pillow (`2451e36`, `a9434c5`)
- **refactor:** League cog configuration management and settings updates (`7d1c892`)
- **fix:** Remove bug where it only counts emojis (`f7f1699`)
- **add:** Message validation functionality (`2e2d9af`)
- **fix:** Contrast issues in leaderboard display (`5e68144`)
- **refactor:** Separate admin commands from main logic (`7ecc422`)
- **refactor:** General league cog improvements (`f4e2502`)
- **fix:** Add star icon for previous winners (`a910081`)

### Database & Technical
- **fix:** Disable statement cache to avoid schema change issues (`a5e922b`)
- **fix:** Change TIMESTAMP to TIMESTAMPTZ for league tables (`27a620a`)
- **fix:** Remove ephemeral flag from stats response (`df9bc1f`)
- **fix:** Update league group description and remove redundant decorators (`0030996`)

---

## AI-Powered Features

### Conversation Generator (Gemini AI)
- **feat:** Add Conversation Cog with AI-generated language learning conversations (`b5675be`)
- **update:** GeminiClient model name to 'gemini-2.0-flash-lite' for free tier compatibility (`876938d`)
- **fix:** Update conversation speaker field names for consistency in embeds (`a81d47c`)

### AI Summaries
- **feat:** Add SummaryCog for AI-powered conversation summaries using Google Gemini API with caching and message link parsing (`561848f`)

---

## Vocabulary Notes System
- **feat:** Implement Vocabulary Notes Cog with database support for managing vocabulary notes (`2c4f8bb`)
- **feat:** Add export command to export vocabulary notes as a CSV file (`0cc1edc`)

---

## Help & Documentation
- **feat:** Add slash command for comprehensive help with categorized bot commands (`35c6192`)
- **docs:** Update README to enhance feature descriptions and command details (`b3bfde2`)

---

## Spotify Integration
- **feat:** Add SpotifyCog to display currently playing songs with user support (`c17e2ea`)
- **add:** Logging to nowplaying command for better debugging (`905083e`)
- **refactor:** Nowplaying embed to include artist name and remove progress display (`dc1993f`)
- **update:** Nowplaying command aliases and enhance embed description format (`750e305`)
- **refactor:** SpotifyCog to use hybrid_command and app_commands for improved command handling (`8d7c17e`)

---

## Introduction Tracking
- **feat:** Add introduction tracking functionality and related database schema (`14816d7`)
- **feat:** Add exemption handling for introduction tracking based on user roles and IDs (`00a08bd`)

---

## Synonyms & Antonyms
- **feat:** Add Synonyms and Antonyms Cog with caching and WordReference integration (`8d56d8a`)

---

## Database & Backend
- **feat:** Implement DatabaseCommands cog with note management functionality (`5f30d9e`)
- **migrate:** Switch to asyncpg for database operations (`5f30d9e`)
- **refactor:** get_safe_username function for improved handling of nicknames and display names (`0cef3dd`)

---

## Quote Generator
- **feat:** Add new quote generation feature with enhanced image styling (`abe65b3`)
- **enhance:** Mention handling in quote generation to display user, role, and channel names instead of IDs (`c2c78d1`)
- **update:** Font size calculations in image creation and change default avatar URL (`c4d3d61`)
- **refactor:** image_creator.py (`cc971cf`)

---

## Conjugation Practice Game
- **feat:** Add conjugation cog with Spanish verb data, game logic, and XML parsing (`55ad244`)

---

## Relay/Admin Commands
- **feat:** Add RelayCog with parrot command for message relaying between guilds and channels (`d438ca2`)

---

## Infrastructure & DevOps

### Docker & Configuration
- **feat:** Add Docker support and refactor configuration management (`d438ca2`)
- **add:** Bot configuration classes and environment selector function (`0156b17`)
- **remove:** dotenv loading from hablemos.py to streamline environment variable management (`219cadd`)

### Logging & Debugging
- **feat:** Add logger setup function (`a4ba8d6`)
- **add:** Environment variable logging for debugging purposes (`8482fa4`)
- **fix:** Logger stderr handling (`a910081`)

### Error Handling
- **refactor:** Error handling in BaseCog to improve command cooldown messaging (`dc93ba0`)
- **refactor:** on_command_error handling (`18292a4`)

---

## Hangman Game

### Core Implementation
- **feat:** Add Hangman game with animal category (`initial commits`)
- **feat:** Add profesiones (professions) category (`08283f3`)
- **feat:** Add ciudades (cities) category (`90753d2`)
- **feat:** Add hangman end-game images (`761b062`)

### Improvements
- **refactor:** Hangman cog structure (`8f78226`)
- **refactor:** Hangman game start logic to simplify error handling (`4c80e7c`)
- **fix:** Reset cooldown for correct guess, added descriptive comments (`fcbebd9`)
- **fix:** Compare hidden word to actual accented word (`71e8258`)
- **fix:** Get winner username from correct context (`790d4b7`)

---

## Conversation Starters
- **feat:** Initial conversation starter implementation with database (`87ddfe6`, `4dd6567`)
- **refactor:** Switch from SQL to CSV for reading questions (`019f937`)
- **fix:** Spanish footer in Spanish topic, English footer in English topic (`730eda8`)
- **fix:** Translation errors and typos (`0d4555a`)

---

## Framework Migration
- **migrate:** Change from Pycord to discord.py (`1e663e2`)
- **update:** Replace imgkit with html2image for B&W images (`b87ceba`)
- **update:** Replace 'emoji' with 'demoji' package (`3bb10db`)

---

## Early Development History

### Initial Setup (First Commits)
- **Initial commit:** Project creation (`e7c7a09`)
- **feat:** Implement cogs structure (`a33ef86`)
- **feat:** Add convo-starter.py and imported discord.py (`0c42a56`)
- **feat:** Add requirements.txt to list bot dependencies (`83d2654`)
- **feat:** Add Procfile for Heroku deployment (`5e6f24b`)
- **feat:** Add ping command and safe_send to check permissions (`03084c0`)
- **feat:** Add info command (`7a0ce45`)
- **feat:** Add invite command (`2587e38`)
- **feat:** Add base cog from which all cogs inherit (`9eb78fb`)
- **feat:** Activate Discord intents (`bf3abaa`)
- **feat:** Add message_content intent (`dd08464`)

### Code Quality
- **refactor:** Code structure for improved readability and maintainability (`d148397`)
- **refactor:** Extension loading in Hablemos class (`eec2af5`)
- **refactor:** Folder structure and naming conventions (`cd31d92`, `69a580a`)
- **cleanup:** Remove old backup files (`a8760b7`)
- **cleanup:** Remove unused helper functions (`7974afb`)

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Total Commits | ~180 |
| Major Features | 12 |
| Bug Fixes | ~40 |
| Refactors | ~30 |
| Documentation | ~10 |

### Major Feature Timeline
1. **Conversation Starters** - Initial bot functionality
2. **Hangman Game** - Interactive word game with categories
3. **Quote Generator** - Create shareable quote images
4. **Synonyms/Antonyms** - WordReference integration
5. **Spotify Integration** - Display now playing
6. **Introduction Tracking** - 30-day duplicate prevention
7. **AI Summaries** - Gemini-powered conversation summaries
8. **AI Conversations** - Generated language learning dialogues
9. **Vocabulary Notes** - Personal vocab management with export
10. **Language League** - Competitive biweekly leaderboards
11. **Website Manager** - External resource management
12. **Exchange Requests** - Language partner matching system

---

## Contributors

Built for the [Spanish-English Learning Server](https://discord.gg/spanish-english).
