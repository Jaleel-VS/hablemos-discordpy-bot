"""
API client for the Spanish-English Discord website backend
"""
import aiohttp
import logging
import os
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

API_BASE_URL = os.getenv(
    'WEBSITE_API_URL',
    'https://spa-eng-discord-website-backend-production.up.railway.app/api'
)


@dataclass
class Podcast:
    id: str
    title: str
    description: str
    image_url: str
    language: str  # 'en', 'es', 'both'
    level: str  # 'beginner', 'intermediate', 'advanced'
    country: str
    topic: str
    url: str
    archived: bool
    created_at: str
    updated_at: str

    @classmethod
    def from_dict(cls, data: dict) -> 'Podcast':
        return cls(
            id=data['id'],
            title=data['title'],
            description=data['description'],
            image_url=data.get('imageUrl', ''),
            language=data['language'],
            level=data['level'],
            country=data['country'],
            topic=data['topic'],
            url=data['url'],
            archived=data.get('archived', False),
            created_at=data.get('createdAt', ''),
            updated_at=data.get('updatedAt', '')
        )


@dataclass
class LinkReportCount:
    podcast_id: str
    count: int

    @classmethod
    def from_dict(cls, data: dict) -> 'LinkReportCount':
        return cls(
            podcast_id=data['podcastId'],
            count=data['count']
        )


class WebsiteAPIClient:
    """Async HTTP client for the website backend API"""

    def __init__(self):
        self.base_url = API_BASE_URL
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict | list | None:
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"

        try:
            async with session.request(method, url, **kwargs) as response:
                if response.status == 204:
                    return None
                if not response.ok:
                    error_text = await response.text()
                    logger.error(f"API error {response.status}: {error_text}")
                    raise Exception(f"API error: {response.status}")
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error: {e}")
            raise

    # ==================== Podcasts ====================

    async def get_podcasts(self, include_archived: bool = False) -> list[Podcast]:
        """Get all podcasts"""
        params = {}
        if include_archived:
            params['includeArchived'] = 'true'

        data = await self._request('GET', '/podcasts', params=params)
        return [Podcast.from_dict(p) for p in (data or [])]

    async def get_podcast(self, podcast_id: str) -> Podcast:
        """Get a single podcast by ID"""
        data = await self._request('GET', f'/podcasts/{podcast_id}')
        return Podcast.from_dict(data)

    async def create_podcast(
        self,
        title: str,
        description: str,
        url: str,
        image_url: str,
        language: str,
        level: str,
        country: str,
        topic: str
    ) -> Podcast:
        """Create a new podcast"""
        payload = {
            'title': title,
            'description': description,
            'url': url,
            'imageUrl': image_url,
            'language': language,
            'level': level,
            'country': country,
            'topic': topic
        }
        data = await self._request('POST', '/podcasts', json=payload)
        return Podcast.from_dict(data)

    async def update_podcast(self, podcast_id: str, **fields) -> Podcast:
        """Update a podcast (partial update)"""
        # Convert snake_case to camelCase for API
        payload = {}
        key_map = {
            'image_url': 'imageUrl',
            'title': 'title',
            'description': 'description',
            'url': 'url',
            'language': 'language',
            'level': 'level',
            'country': 'country',
            'topic': 'topic'
        }
        for key, value in fields.items():
            if value is not None:
                api_key = key_map.get(key, key)
                payload[api_key] = value

        data = await self._request('PATCH', f'/podcasts/{podcast_id}', json=payload)
        return Podcast.from_dict(data)

    async def delete_podcast(self, podcast_id: str) -> None:
        """Delete a podcast"""
        await self._request('DELETE', f'/podcasts/{podcast_id}')

    async def archive_podcast(self, podcast_id: str) -> Podcast:
        """Archive a podcast"""
        data = await self._request('POST', f'/podcasts/{podcast_id}/archive')
        return Podcast.from_dict(data)

    async def unarchive_podcast(self, podcast_id: str) -> Podcast:
        """Unarchive a podcast"""
        data = await self._request('POST', f'/podcasts/{podcast_id}/unarchive')
        return Podcast.from_dict(data)

    # ==================== Link Reports ====================

    async def get_link_report_counts(self) -> list[LinkReportCount]:
        """Get report counts for all podcasts"""
        data = await self._request('GET', '/link-reports/counts')
        return [LinkReportCount.from_dict(r) for r in (data or [])]

    async def get_podcast_report_count(self, podcast_id: str) -> int:
        """Get report count for a specific podcast"""
        data = await self._request('GET', f'/podcasts/{podcast_id}/reports/count')
        return data.get('count', 0) if data else 0

    async def clear_podcast_reports(self, podcast_id: str) -> None:
        """Clear all reports for a podcast"""
        await self._request('DELETE', f'/podcasts/{podcast_id}/reports')
