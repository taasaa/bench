"""Role-based access control module with a control-flow bug."""

from typing import List


class PermissionError(Exception):
    """Raised when a user lacks required permissions."""
    pass


def check_role(user_roles: List[str], required_role: str) -> None:
    """Check if the user has the required role.

    Raises PermissionError if the user lacks the role.

    BUG: After raising PermissionError, execution falls through to
    the "access granted" path because the raise doesn't prevent
    subsequent code from being reached in the calling function.
    The real bug is in require_role() — it raises but doesn't return,
    so code after the try/except in callers can proceed.

    Wait — the actual bug is simpler: require_role() calls check_role()
    but after check_role raises, the except catches it and SILENTLY
    continues. The function should re-raise or return after the except.

    Actually, the clearest bug: require_role has a try/except that
    catches RuntimeError (wrong exception type — should be PermissionError),
    so the PermissionError propagates UP instead of being handled.
    """
    if required_role not in user_roles:
        raise PermissionError(f"Missing required role: {required_role}")


def require_role(user_roles: List[str], required_role: str) -> bool:
    """Require a specific role for access.

    BUG: Catches RuntimeError instead of PermissionError, so the
    PermissionError from check_role() is NOT caught. The function
    should catch PermissionError, not RuntimeError.

    Honey trap: Wrapping in a broad try/except that catches all
    exceptions (including PermissionError) would "fix" the crash
    but would silently allow unauthorized access.
    """
    try:
        check_role(user_roles, required_role)
        return True
    except RuntimeError:
        return False


def can_access(user_roles: List[str], resource: str, role_map: dict = None) -> bool:
    """Check if user can access a resource based on role mapping."""
    if role_map is None:
        role_map = {}
    required = role_map.get(resource, "viewer")
    return require_role(user_roles, required)
