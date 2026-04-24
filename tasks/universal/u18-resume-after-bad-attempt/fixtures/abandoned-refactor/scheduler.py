"""Task scheduler with priority queue — abandoned refactor."""

import heapq
from datetime import datetime


class TaskScheduler:
    """Schedule tasks by priority with deadline awareness."""

    def __init__(self):
        self._queue = []
        self._tasks = {}

    def add_task(self, task_id: str, priority: int, deadline: str) -> None:
        """Add a task with priority and ISO-format deadline."""
        self._tasks[task_id] = {"priority": priority, "deadline": deadline}
        heapq.heappush(self._queue, (-priority, task_id))

    def get_next(self) -> dict | None:
        """Return the highest-priority task that hasn't expired."""
        while self._queue:
            _, task_id = heapq.heappop(self._queue)
            task = self._tasks.get(task_id)
            if task is None:
                continue
            # BUG: string comparison — lexicographic instead of datetime
            if task["deadline"] > datetime.now().isoformat():
                return task
        return None

    def cancel_task(self, task_id: str) -> bool:
        """Remove a task from the scheduler."""
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False

    def pending_count(self) -> int:
        """Return number of pending tasks."""
        return len(self._tasks)

    # DEAD CODE: abandoned refactor attempt
    # def get_next_v2(self):
    #     # I was going to store parsed datetimes in _tasks
    #     # but that changes the add_task contract
    #     pass
