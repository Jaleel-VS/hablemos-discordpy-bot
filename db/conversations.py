
from db import DatabaseMixin

class ConversationsMixin(DatabaseMixin):
    async def add_conversation(self, language: str, level: str, category: str,
                              scenario_intro: str, speaker1_name: str,
                              speaker2_name: str, conversation_text: str) -> int:
        """Add a generated conversation to the database"""
        row = await self._fetchrow('''
            INSERT INTO conversations
            (language, level, category, scenario_intro, speaker1_name,
             speaker2_name, conversation_text)
            VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
        ''', language, level, category, scenario_intro, speaker1_name,
             speaker2_name, conversation_text)
        return row['id']

    async def get_random_conversation(self, language: str, level: str,
                                      category: str) -> dict | None:
        """Get a random conversation, preferring less-used ones"""
        row = await self._fetchrow('''
            SELECT id, language, level, category, scenario_intro,
                   speaker1_name, speaker2_name, conversation_text, usage_count
            FROM conversations
            WHERE language = $1 AND level = $2 AND category = $3
            ORDER BY usage_count ASC, RANDOM() LIMIT 1
        ''', language, level, category)
        return dict(row) if row else None

    async def increment_conversation_usage(self, conversation_id: int) -> None:
        """Increment usage count and update last_used_at"""
        await self._execute('''
            UPDATE conversations
            SET usage_count = usage_count + 1, last_used_at = NOW()
            WHERE id = $1
        ''', conversation_id)

    async def check_regeneration_needed(self, language: str, level: str,
                                       category: str) -> bool:
        """Check if all conversations in a combo have been used at least once"""
        result = await self._fetchrow('''
            SELECT COUNT(*) as total, MIN(usage_count) as min_usage
            FROM conversations
            WHERE language = $1 AND level = $2 AND category = $3
        ''', language, level, category)
        if not result or result['total'] == 0:
            return False
        return result['min_usage'] > 0

    async def get_conversation_count(self, language: str = None, level: str = None,
                                    category: str = None) -> int:
        """Get count of conversations matching criteria"""
        if language and level and category:
            count = await self._fetchval('''
                SELECT COUNT(*) FROM conversations
                WHERE language = $1 AND level = $2 AND category = $3
            ''', language, level, category)
        else:
            count = await self._fetchval('SELECT COUNT(*) FROM conversations')
        return count or 0

    async def delete_old_conversations(self, language: str, level: str,
                                      category: str) -> int:
        """Delete old conversations for a specific combo (for regeneration)"""
        result = await self._execute('''
            DELETE FROM conversations
            WHERE language = $1 AND level = $2 AND category = $3
        ''', language, level, category)
        return int(result.split()[-1]) if result and result.split() else 0

    async def check_daily_limit(self, user_id: int, limit: int = 2) -> int:
        """Check how many conversations a user has requested today"""
        row = await self._fetchrow('''
            SELECT conversation_count
            FROM user_conversation_limits
            WHERE user_id = $1 AND date = CURRENT_DATE
        ''', user_id)
        return row['conversation_count'] if row else 0

    async def increment_daily_usage(self, user_id: int) -> None:
        """Increment a user's daily conversation count"""
        await self._execute('''
            INSERT INTO user_conversation_limits (user_id, date, conversation_count)
            VALUES ($1, CURRENT_DATE, 1)
            ON CONFLICT (user_id) DO UPDATE
            SET conversation_count = CASE
                WHEN user_conversation_limits.date = CURRENT_DATE
                THEN user_conversation_limits.conversation_count + 1
                ELSE 1 END,
                date = CURRENT_DATE
        ''', user_id)

    async def get_daily_usage_remaining(self, user_id: int, limit: int = 2) -> int:
        """Get how many conversations a user has remaining today"""
        used = await self.check_daily_limit(user_id, limit)
        return max(0, limit - used)
