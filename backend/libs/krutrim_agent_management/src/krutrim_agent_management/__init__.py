"""Pluggable persistence layer: projects, agent memory, sessions, a result
cache, and auth users.

`Storage` and `AuthStorage` are the backend-agnostic contracts; `LocalStorage`
/ `LocalAuthStorage` (SQLite + filesystem) are the only implementations today.
"""

from krutrim_agent_management.blob_storage.blobstore import BlobStore, LocalBlobStore
from krutrim_agent_management.constants import LOCAL_USER_ID
from krutrim_agent_management.models import (
    Agent,
    Chat,
    OwnerType,
    Project,
    Role,
    SessionInfo,
    SharingScope,
    UserRecord,
)
from krutrim_agent_management.storage.auth_base import (
    AuthStorage,
    EmailTakenError,
    UsernameTakenError,
)
from krutrim_agent_management.storage.base import Storage
from krutrim_agent_management.storage.local import LocalAuthStorage, LocalStorage
from krutrim_agent_management.storage_factory import create_auth_storage, create_storage

__all__ = [
    "LOCAL_USER_ID",
    "Agent",
    "AuthStorage",
    "BlobStore",
    "Chat",
    "EmailTakenError",
    "LocalAuthStorage",
    "LocalBlobStore",
    "LocalStorage",
    "OwnerType",
    "Project",
    "Role",
    "SessionInfo",
    "SharingScope",
    "Storage",
    "UserRecord",
    "UsernameTakenError",
    "create_auth_storage",
    "create_storage",
]
