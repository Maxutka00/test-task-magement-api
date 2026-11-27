from enum import StrEnum

from app.core.exceptions import BadRequestError


class Permission(StrEnum):
    TASK_READ = "task:read"
    TASK_CREATE = "task:create"
    TASK_EDIT_ANY = "task:edit_any"
    TASK_CHANGE_STATUS_ANY = "task:change_status_any"
    TASK_DELETE = "task:delete"
    COMMENT_CREATE = "comment:create"
    TEAM_INVITE = "team:invite"
    TEAM_KICK_MEMBERS = "team:kick_members"
    ROLE_CREATE = "role:create"
    ROLE_EDIT = "role:edit"
    ROLE_ASSIGN = "role:assign"


ADMIN_ROLE_NAME = "admin"
MANAGER_ROLE_NAME = "manager"
USER_ROLE_NAME = "user"

ADMIN_ROLE_LEVEL = 100
MANAGER_ROLE_LEVEL = 50
USER_ROLE_LEVEL = 10

TASK_READ_DEPENDENT_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.TASK_CREATE,
        Permission.TASK_EDIT_ANY,
        Permission.TASK_CHANGE_STATUS_ANY,
        Permission.TASK_DELETE,
        Permission.COMMENT_CREATE,
    }
)

DEFAULT_USER_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.TASK_READ,
        Permission.TASK_CREATE,
        Permission.COMMENT_CREATE,
    }
)

DEFAULT_MANAGER_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.TASK_READ,
        Permission.TASK_CREATE,
        Permission.TASK_EDIT_ANY,
        Permission.TASK_CHANGE_STATUS_ANY,
        Permission.TASK_DELETE,
        Permission.COMMENT_CREATE,
        Permission.TEAM_INVITE,
    }
)

DEFAULT_ADMIN_PERMISSIONS: frozenset[Permission] = frozenset(Permission)


def validate_permission_dependencies(permissions: set[Permission]) -> None:
    if (permissions & TASK_READ_DEPENDENT_PERMISSIONS) and Permission.TASK_READ not in permissions:
        raise BadRequestError("Task and comment permissions require task:read")
