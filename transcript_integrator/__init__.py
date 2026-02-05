"""
Transcript Integrator Module

This module provides functionality for:
- Monitoring a landing folder for new transcript files
- Interactive file renaming with meeting metadata
- LLM-powered extraction of meeting information (members, projects, topics, tasks)
- Database integration with fuzzy matching
- Database tools for chatbot retrieval, editing, and creation
"""

from .models import (
    Committee,
    Meeting,
    MeetingMembers,
    MeetingProjects,
    MeetingTopics,
    MeetingTasks,
    Project,
    ProjectMembers,
    ProjectTasks,
    Task,
    TaskMembers,
    Topic,
)
from .integrator import TranscriptIntegrator
from .file_watcher import FileWatcher, FileWatcherHandler
from .database_tools import DatabaseTools, ToolExecutor, TOOL_DEFINITIONS

__all__ = [
    "Committee",
    "Meeting",
    "MeetingMembers",
    "MeetingProjects",
    "MeetingTopics",
    "MeetingTasks",
    "Project",
    "ProjectMembers",
    "ProjectTasks",
    "Task",
    "TaskMembers",
    "Topic",
    "TranscriptIntegrator",
    "FileWatcher",
    "FileWatcherHandler",
    "DatabaseTools",
    "ToolExecutor",
    "TOOL_DEFINITIONS",
]
