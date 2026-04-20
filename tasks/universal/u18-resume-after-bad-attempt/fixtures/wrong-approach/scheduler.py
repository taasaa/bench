"""Task scheduler with priority queue — wrong approach attempted."""
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
            # BUG: string comparison fails for different date formats
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


# WRONG APPROACH: tried to fix by converting everything to timestamps
# This breaks the API — callers expect ISO strings back
def _to_timestamp(deadline_str: str) -> float:
    """Convert deadline to timestamp. WRONG: don't use this."""
    try:
        return datetime.fromisoformat(deadline_str).timestamp()
    except ValueError:
        return 0.0
