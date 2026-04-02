"""Database mixin for task management queries."""
import logging

from db import DatabaseMixin

logger = logging.getLogger(__name__)


class TasksMixin(DatabaseMixin):
    """Task CRUD operations."""

    async def create_task(
        self,
        guild_id: int,
        title: str,
        description: str,
        created_by: int,
        assignee_ids: list[int] | None = None,
    ) -> dict:
        """Create a task and return the row."""
        row = await self._fetchrow(
            """
            INSERT INTO tasks (guild_id, title, description, created_by, assignee_ids)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            guild_id,
            title,
            description,
            created_by,
            assignee_ids or [],
        )
        return dict(row)

    async def get_task(self, task_id: int) -> dict | None:
        """Fetch a single task by ID."""
        row = await self._fetchrow("SELECT * FROM tasks WHERE id = $1", task_id)
        return dict(row) if row else None

    async def update_task_status(self, task_id: int, status: str) -> dict | None:
        """Update task status and return updated row."""
        row = await self._fetchrow(
            """
            UPDATE tasks SET status = $2, updated_at = NOW()
            WHERE id = $1 RETURNING *
            """,
            task_id,
            status,
        )
        return dict(row) if row else None

    async def update_task_assignees(
        self, task_id: int, assignee_ids: list[int],
    ) -> dict | None:
        """Replace assignees and return updated row."""
        row = await self._fetchrow(
            """
            UPDATE tasks SET assignee_ids = $2, updated_at = NOW()
            WHERE id = $1 RETURNING *
            """,
            task_id,
            assignee_ids,
        )
        return dict(row) if row else None

    async def update_task_message(self, task_id: int, message_id: int) -> None:
        """Store the Discord message ID for a task embed."""
        await self._execute(
            "UPDATE tasks SET message_id = $2 WHERE id = $1",
            task_id,
            message_id,
        )

    async def list_tasks(
        self,
        guild_id: int,
        status: str | None = None,
        assignee_id: int | None = None,
    ) -> list[dict]:
        """List tasks with optional filters."""
        query = "SELECT * FROM tasks WHERE guild_id = $1"
        args: list = [guild_id]
        idx = 2

        if status:
            query += f" AND status = ${idx}"
            args.append(status)
            idx += 1

        if assignee_id:
            query += f" AND ${idx} = ANY(assignee_ids)"
            args.append(assignee_id)
            idx += 1

        query += " ORDER BY created_at DESC"
        rows = await self._fetch(query, *args)
        return [dict(r) for r in rows]

    async def delete_task(self, task_id: int) -> bool:
        """Delete a task. Returns True if a row was deleted."""
        result = await self._execute("DELETE FROM tasks WHERE id = $1", task_id)
        return result == "DELETE 1"
