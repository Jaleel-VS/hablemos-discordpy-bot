
from db import DatabaseMixin

class SettingsMixin(DatabaseMixin):
    async def get_bot_setting(self, setting_key: str) -> int | None:
        """Get a bot setting value by key"""
        row = await self._fetchrow(
            'SELECT setting_value FROM bot_settings WHERE setting_key = $1', setting_key,
        )
        return row['setting_value'] if row else None

    async def set_bot_setting(self, setting_key: str, setting_value: int) -> bool:
        """Set a bot setting value (upsert)"""
        await self._execute('''
            INSERT INTO bot_settings (setting_key, setting_value)
            VALUES ($1, $2)
            ON CONFLICT (setting_key) DO UPDATE SET setting_value = $2
        ''', setting_key, setting_value)
        return True

    async def get_feature_setting(self, feature_name: str) -> bool:
        """Get whether a feature is enabled"""
        row = await self._fetchrow(
            'SELECT enabled FROM feature_settings WHERE feature_name = $1', feature_name,
        )
        return row['enabled'] if row else False

    async def set_feature_setting(self, feature_name: str, enabled: bool) -> bool:
        """Set whether a feature is enabled"""
        await self._execute('''
            INSERT INTO feature_settings (feature_name, enabled)
            VALUES ($1, $2)
            ON CONFLICT (feature_name) DO UPDATE SET enabled = $2
        ''', feature_name, enabled)
        return True
