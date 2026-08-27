from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


AgentTerminalSessionStatus = Literal[
    "starting",
    "running",
    "exited",
    "terminated",
    "failed",
]
AgentTerminalGitChangeScope = Literal[
    "staged",
    "unstaged",
    "untracked",
    "conflicted",
]
AgentTerminalGitChangeKind = Literal[
    "added",
    "copied",
    "deleted",
    "modified",
    "renamed",
    "type_changed",
    "untracked",
    "conflicted",
]
AgentTerminalGitRefKind = Literal[
    "local_branch",
    "remote_branch",
    "tag",
]


class AgentTerminalRootResponse(BaseModel):
    key: str
    label: str
    path: str


class AgentTerminalConfigResponse(BaseModel):
    enabled: bool
    codex_available: bool
    tmux_available: bool
    roots: list[AgentTerminalRootResponse] = Field(default_factory=list)
    max_sessions_per_user: int


class AgentTerminalSessionCreateRequest(BaseModel):
    root_key: str = Field(min_length=1, max_length=64)
    cols: int = Field(default=120, ge=20, le=500)
    rows: int = Field(default=36, ge=5, le=200)


class AgentTerminalSessionResponse(BaseModel):
    id: str
    tool: Literal["codex"] = "codex"
    root_key: str
    root_path: str
    status: AgentTerminalSessionStatus
    exit_code: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None


class AgentTerminalSessionListResponse(BaseModel):
    items: list[AgentTerminalSessionResponse] = Field(default_factory=list)


class AgentTerminalGitChangeResponse(BaseModel):
    path: str
    old_path: str | None = None
    scope: AgentTerminalGitChangeScope
    kind: AgentTerminalGitChangeKind


class AgentTerminalGitStatusResponse(BaseModel):
    is_repository: bool
    branch: str | None = None
    head: str | None = None
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    changes: list[AgentTerminalGitChangeResponse] = Field(default_factory=list)
    truncated: bool = False


class AgentTerminalGitDiffResponse(BaseModel):
    path: str
    old_path: str | None = None
    scope: AgentTerminalGitChangeScope
    kind: AgentTerminalGitChangeKind
    old_content: str | None = None
    new_content: str | None = None
    is_binary: bool = False
    too_large: bool = False


class AgentTerminalGitRefResponse(BaseModel):
    name: str
    full_name: str
    kind: AgentTerminalGitRefKind
    target: str
    current: bool = False


class AgentTerminalGitStashResponse(BaseModel):
    ref: str
    sha: str
    subject: str


class AgentTerminalGitSummaryResponse(BaseModel):
    is_repository: bool
    refs: list[AgentTerminalGitRefResponse] = Field(default_factory=list)
    stashes: list[AgentTerminalGitStashResponse] = Field(default_factory=list)
    refs_truncated: bool = False
    stashes_truncated: bool = False


class AgentTerminalGitCommitResponse(BaseModel):
    sha: str
    parents: list[str] = Field(default_factory=list)
    author_name: str
    authored_at: datetime
    subject: str


class AgentTerminalGitHistoryResponse(BaseModel):
    items: list[AgentTerminalGitCommitResponse] = Field(default_factory=list)
    offset: int
    has_more: bool = False


class AgentTerminalGitCommitFileResponse(BaseModel):
    path: str
    old_path: str | None = None
    kind: AgentTerminalGitChangeKind


class AgentTerminalGitCommitDetailResponse(AgentTerminalGitCommitResponse):
    files: list[AgentTerminalGitCommitFileResponse] = Field(default_factory=list)
    files_truncated: bool = False


class AgentTerminalGitCommitDiffResponse(BaseModel):
    commit: str
    path: str
    old_path: str | None = None
    kind: AgentTerminalGitChangeKind
    old_content: str | None = None
    new_content: str | None = None
    is_binary: bool = False
    too_large: bool = False
