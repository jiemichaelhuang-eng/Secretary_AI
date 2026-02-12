"""
Database Tools for Secretary AI Chatbot

Provides functions for:
- RETRIEVAL: Query data across related tables
- EDITING: Update allowed fields (task_status, task_members)
- CREATION: Add new rows to allowed tables

All functions are async and use SQLAlchemy with PostgreSQL.
"""

import os
import json
import difflib
import logging
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Tuple, Union

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update, delete, and_, or_, func
from sqlalchemy.orm import selectinload

from .models import (
    Base,
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

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

# Ensure async driver
if DATABASE_URL:
    if DATABASE_URL.startswith('postgresql://'):
        DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+asyncpg://', 1)
    elif DATABASE_URL.startswith('postgresql+psycopg2://'):
        DATABASE_URL = DATABASE_URL.replace('postgresql+psycopg2://', 'postgresql+asyncpg://', 1)


# ============================================================================
# OpenAI Function Definitions (Tool Schemas)
# ============================================================================

TOOL_DEFINITIONS = [
    # -------------------- RETRIEVAL TOOLS --------------------
    {
        "type": "function",
        "function": {
            "name": "get_my_tasks",
            "description": "Get all tasks assigned to the current user (the person chatting). Returns task details including name, description, deadline, and status.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Get the current date and time according to the server where the bot is running.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_identity",
            "description": "Identify who the current Discord user is in the Business Analytics Students Society. Returns their name, role, subcommittee, email, and Discord ID.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_tasks",
            "description": "Get all tasks in the system, optionally filtered by status (complete/incomplete).",
            "parameters": {
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "description": "Filter by status: 'complete', 'incomplete', or 'all'",
                        "enum": ["complete", "incomplete", "all"]
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_member_info",
            "description": "Get information about a committee member by name, including email, role, subcommittee, and Discord ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_name": {
                        "type": "string",
                        "description": "The name of the member to look up (fuzzy matching supported)"
                    }
                },
                "required": ["member_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_meeting_info",
            "description": "Get information about a meeting including summary, attendees, topics discussed, and tasks assigned. Can search by name or ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "meeting_identifier": {
                        "type": "string",
                        "description": "Meeting name (partial match) or meeting ID"
                    }
                },
                "required": ["meeting_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_meetings_for_member",
            "description": "Get all meetings that a specific member attended.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_name": {
                        "type": "string",
                        "description": "The name of the member"
                    }
                },
                "required": ["member_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_missed_meetings",
            "description": "Get meetings that the current user did NOT attend, along with what was covered.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_info",
            "description": "Get information about a project including description, team members, and related tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "The name of the project (fuzzy matching supported)"
                    }
                },
                "required": ["project_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_projects",
            "description": "Get a list of all projects in the system.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_members",
            "description": "Get a list of all committee members.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_topic_info",
            "description": "Get information about a topic and which meetings discussed it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_name": {
                        "type": "string",
                        "description": "The name of the topic"
                    }
                },
                "required": ["topic_name"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "search_database",
            "description": "General search across the database for any information. Use this when other specific tools don't fit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_query": {
                        "type": "string",
                        "description": "What to search for"
                    },
                    "search_in": {
                        "type": "string",
                        "description": "Where to search: 'members', 'meetings', 'projects', 'tasks', 'topics', or 'all'",
                        "enum": ["members", "meetings", "projects", "tasks", "topics", "all"]
                    }
                },
                "required": ["search_query"]
            }
        }
    },
    
    # -------------------- EDIT TOOLS --------------------
    {
        "type": "function",
        "function": {
            "name": "update_task_status",
            "description": "Update a task's status to 'complete' or 'incomplete'. Use when user says they finished a task or need to reopen one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_identifier": {
                        "type": "string",
                        "description": "Task name (partial match) or task ID"
                    },
                    "new_status": {
                        "type": "string",
                        "description": "New status: 'complete' or 'incomplete'",
                        "enum": ["complete", "incomplete"]
                    }
                },
                "required": ["task_identifier", "new_status"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "assign_member_to_task",
            "description": "Assign a committee member to an existing task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_identifier": {
                        "type": "string",
                        "description": "Task name (partial match) or task ID"
                    },
                    "member_name": {
                        "type": "string",
                        "description": "Name of the member to assign"
                    }
                },
                "required": ["task_identifier", "member_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remove_member_from_task",
            "description": "Remove a committee member from a task assignment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_identifier": {
                        "type": "string",
                        "description": "Task name (partial match) or task ID"
                    },
                    "member_name": {
                        "type": "string",
                        "description": "Name of the member to remove"
                    }
                },
                "required": ["task_identifier", "member_name"]
            }
        }
    },
    
    # -------------------- CREATE TOOLS --------------------
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a new task. Use this whenever the user says they are starting/creating a task. If any required information is missing, ask the user for it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "Name/title of the task"
                    },
                    "task_description": {
                        "type": "string",
                        "description": "Detailed description of what needs to be done"
                    },
                    "deadline": {
                        "type": "string",
                        "description": "Deadline in YYYY-MM-DD format, or null if none"
                    },
                    "assigned_to": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of member names to assign this task to. If the user says things like 'for me', you can either put their member name here or set assign_to_current_user=true."
                    },
                    "assign_to_current_user": {
                        "type": "boolean",
                        "description": "Set to true when the user clearly wants the task assigned to themselves (e.g. 'I'm starting a new task for me')."
                    }
                },
                "required": ["task_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_project",
            "description": "Create a new project with optional team members.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Name of the project"
                    },
                    "project_description": {
                        "type": "string",
                        "description": "Description of the project"
                    },
                    "team_members": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of member names to add to this project"
                    }
                },
                "required": ["project_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_member_to_project",
            "description": "Add a committee member to an existing project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Name of the project"
                    },
                    "member_name": {
                        "type": "string",
                        "description": "Name of the member to add"
                    }
                },
                "required": ["project_name", "member_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_topic",
            "description": "Create a new discussion topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_name": {
                        "type": "string",
                        "description": "Name of the topic"
                    },
                    "topic_description": {
                        "type": "string",
                        "description": "Description of the topic"
                    }
                },
                "required": ["topic_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_topic_to_meeting",
            "description": "Link an existing or new topic to a meeting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "meeting_identifier": {
                        "type": "string",
                        "description": "Meeting name or ID"
                    },
                    "topic_name": {
                        "type": "string",
                        "description": "Name of the topic to link"
                    }
                },
                "required": ["meeting_identifier", "topic_name"]
            }
        }
    },
]


# ============================================================================
# Database Tools Class
# ============================================================================

class DatabaseTools:
    """
    Provides database operations for the chatbot.
    All methods are async and handle their own sessions.
    """
    
    def __init__(self):
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL not found in environment variables.")
        
        self.engine = create_async_engine(DATABASE_URL, echo=False, future=True)
        self.async_session = sessionmaker(
            self.engine, 
            expire_on_commit=False, 
            class_=AsyncSession
        )
        
        # Cache for member lookup (populated on first use)
        # _member_cache: full_name_lower -> member dict
        # _member_first_name_index: first_name_lower -> list[member dict]
        self._member_cache: Dict[str, Dict[str, Any]] = {}
        self._member_first_name_index: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_loaded = False
    
    async def _ensure_cache(self):
        """Load member cache if not already loaded."""
        if self._cache_loaded:
            return
        
        async with self.async_session() as session:
            result = await session.execute(
                select(Committee.member_id, Committee.member_name, Committee.discord_id, Committee.role, Committee.subcommittee, Committee.email)
            )
            for member_id, name, discord_id, role, subcommittee, email in result.fetchall():
                if not name:
                    continue
                
                member_dict = {
                    'id': member_id,
                    'name': name,
                    'discord_id': discord_id,
                    'role': role,
                    'subcommittee': subcommittee,
                    'email': email,
                }
                
                # Cache by full name
                self._member_cache[name.lower()] = member_dict
                
                # Cache by first name for nicer "who is michael / sam / andy" queries
                first_name = name.split()[0].lower()
                self._member_first_name_index.setdefault(first_name, []).append(member_dict)
        self._cache_loaded = True
    
    def _fuzzy_match_member(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Fuzzy match a member name to the cache.
        
        Supports:
        - Full name lookups (e.g. "Andy Shang")
        - First name lookups when unique (e.g. "Sam", "Michael")
        - Noisy strings that include extra commentary, e.g.
          "Michael Huang (the coolest person in the world!)"
        """
        raw = (name or "").strip()
        if not raw:
            return None
        
        # Strip common trailing commentary in parentheses, etc.
        cleaned = raw.split("(", 1)[0].strip()
        cleaned = cleaned.rstrip(",;.-").strip()
        key = cleaned.lower()
        
        # 1) Exact full-name match
        if key in self._member_cache:
            return self._member_cache[key]
        
        # 2) Single-word (first-name-only) queries when unique
        if " " not in key:
            first_name_matches = self._member_first_name_index.get(key, [])
            if len(first_name_matches) == 1:
                return first_name_matches[0]
            # If 0 or >1 matches, fall through to fuzzy full-name match
        
        # 3) Fuzzy match on full names
        matches = difflib.get_close_matches(key, list(self._member_cache.keys()), n=1, cutoff=0.6)
        if matches:
            return self._member_cache[matches[0]]
        
        return None
    
    async def get_member_by_discord_id(self, discord_id: int) -> Optional[Dict[str, Any]]:
        """Get member info by Discord ID."""
        await self._ensure_cache()
        
        async with self.async_session() as session:
            result = await session.execute(
                select(Committee).where(Committee.discord_id == discord_id)
            )
            member = result.scalar_one_or_none()
            
            if member:
                return {
                    'id': member.member_id,
                    'name': member.member_name,
                    'email': member.email,
                    'role': member.role,
                    'subcommittee': member.subcommittee,
                    'discord_id': member.discord_id
                }
        return None
    
    # -------------------- RETRIEVAL FUNCTIONS --------------------
    
    async def get_my_identity(self, discord_id: int) -> Dict[str, Any]:
        """Return identity information for the current Discord user."""
        member = await self.get_member_by_discord_id(discord_id)
        if not member:
            return {
                "error": "Could not find your member record. Your Discord account may not be linked in the committee table."
            }
        return {
            "message": f"You are {member['name']} in the society.",
            "member": member,
        }
    
    async def get_my_tasks(self, discord_id: int) -> Dict[str, Any]:
        """Get tasks for a specific user by their Discord ID."""
        await self._ensure_cache()
        
        member = await self.get_member_by_discord_id(discord_id)
        if not member:
            return {"error": "Could not find your member record. Please contact an admin to link your Discord account."}
        
        async with self.async_session() as session:
            # Get tasks through task_members junction
            result = await session.execute(
                select(Task, TaskMembers)
                .join(TaskMembers, Task.task_id == TaskMembers.task_id)
                .where(TaskMembers.member_id == member['id'])
                .order_by(Task.task_deadline.asc().nullslast())
            )
            
            tasks = []
            for task, _ in result.fetchall():
                tasks.append({
                    'task_id': task.task_id,
                    'name': task.task_name,
                    'description': task.task_description,
                    'deadline': str(task.task_deadline) if task.task_deadline else None,
                    'status': task.task_status or 'incomplete'
                })
            
            if not tasks:
                return {"message": f"You ({member['name']}) have no tasks assigned.", "tasks": []}
            
            return {
                "message": f"Found {len(tasks)} task(s) for {member['name']}",
                "tasks": tasks
            }
    
    async def get_all_tasks(self, status_filter: str = "all") -> Dict[str, Any]:
        """Get all tasks, optionally filtered by status."""
        async with self.async_session() as session:
            query = select(Task)
            
            if status_filter == "complete":
                query = query.where(Task.task_status == 'complete')
            elif status_filter == "incomplete":
                query = query.where(or_(Task.task_status == 'incomplete', Task.task_status == None))
            
            query = query.order_by(Task.task_deadline.asc().nullslast())
            result = await session.execute(query)
            
            tasks = []
            for task in result.scalars():
                # Get assigned members
                members_result = await session.execute(
                    select(Committee.member_name)
                    .join(TaskMembers, Committee.member_id == TaskMembers.member_id)
                    .where(TaskMembers.task_id == task.task_id)
                )
                assigned_to = [m[0] for m in members_result.fetchall()]
                
                tasks.append({
                    'task_id': task.task_id,
                    'name': task.task_name,
                    'description': task.task_description,
                    'deadline': str(task.task_deadline) if task.task_deadline else None,
                    'status': task.task_status or 'incomplete',
                    'assigned_to': assigned_to
                })
            
            return {
                "message": f"Found {len(tasks)} task(s)" + (f" with status '{status_filter}'" if status_filter != "all" else ""),
                "tasks": tasks
            }
    
    async def get_member_info(self, member_name: str) -> Dict[str, Any]:
        """Get detailed info about a member."""
        await self._ensure_cache()
        
        matched = self._fuzzy_match_member(member_name)
        if not matched:
            return {"error": f"Could not find a member matching '{member_name}'"}
        
        async with self.async_session() as session:
            result = await session.execute(
                select(Committee).where(Committee.member_id == matched['id'])
            )
            member = result.scalar_one_or_none()
            
            if not member:
                return {"error": f"Member record not found"}
            
            # Get their projects
            projects_result = await session.execute(
                select(Project.project_name)
                .join(ProjectMembers, Project.project_id == ProjectMembers.project_id)
                .where(ProjectMembers.member_id == member.member_id)
            )
            projects = [p[0] for p in projects_result.fetchall()]
            
            # Get their tasks
            tasks_result = await session.execute(
                select(Task.task_name, Task.task_status)
                .join(TaskMembers, Task.task_id == TaskMembers.task_id)
                .where(TaskMembers.member_id == member.member_id)
            )
            tasks = [{"name": t[0], "status": t[1] or 'incomplete'} for t in tasks_result.fetchall()]
            
            return {
                "member_id": member.member_id,
                "name": member.member_name,
                "email": member.email,
                "role": member.role,
                "subcommittee": member.subcommittee,
                "discord_id": member.discord_id,
                "projects": projects,
                "tasks": tasks
            }
    
    async def get_meeting_info(self, meeting_identifier: str) -> Dict[str, Any]:
        """Get detailed info about a meeting."""
        async with self.async_session() as session:
            # Try to find by ID first
            meeting = None
            try:
                meeting_id = int(meeting_identifier)
                result = await session.execute(
                    select(Meeting).where(Meeting.meeting_id == meeting_id)
                )
                meeting = result.scalar_one_or_none()
            except ValueError:
                pass
            
            # If not found by ID, search by name
            if not meeting:
                result = await session.execute(
                    select(Meeting).where(
                        Meeting.meeting_name.ilike(f"%{meeting_identifier}%")
                    )
                )
                meetings = result.scalars().all()
                if len(meetings) == 1:
                    meeting = meetings[0]
                elif len(meetings) > 1:
                    return {
                        "error": "Multiple meetings match that name",
                        "matches": [{"id": m.meeting_id, "name": m.meeting_name} for m in meetings[:5]]
                    }
            
            if not meeting:
                return {"error": f"Could not find a meeting matching '{meeting_identifier}'"}
            
            # Get attendees
            attendees_result = await session.execute(
                select(Committee.member_name)
                .join(MeetingMembers, Committee.member_id == MeetingMembers.member_id)
                .where(MeetingMembers.meeting_id == meeting.meeting_id)
            )
            attendees = [a[0] for a in attendees_result.fetchall()]
            
            # Get topics
            topics_result = await session.execute(
                select(Topic.topic_name)
                .join(MeetingTopics, Topic.topic_id == MeetingTopics.topic_id)
                .where(MeetingTopics.meeting_id == meeting.meeting_id)
            )
            topics = [t[0] for t in topics_result.fetchall()]
            
            # Get tasks assigned in this meeting
            tasks_result = await session.execute(
                select(Task.task_name, Task.task_status)
                .join(MeetingTasks, Task.task_id == MeetingTasks.task_id)
                .where(MeetingTasks.meeting_id == meeting.meeting_id)
            )
            tasks = [{"name": t[0], "status": t[1] or 'incomplete'} for t in tasks_result.fetchall()]
            
            # Get related projects
            projects_result = await session.execute(
                select(Project.project_name)
                .join(MeetingProjects, Project.project_id == MeetingProjects.project_id)
                .where(MeetingProjects.meeting_id == meeting.meeting_id)
            )
            projects = [p[0] for p in projects_result.fetchall()]
            
            return {
                "meeting_id": meeting.meeting_id,
                "name": meeting.meeting_name,
                "type": meeting.meeting_type,
                "summary": meeting.meeting_summary,
                "date": str(meeting.ingestion_timestamp.date()) if meeting.ingestion_timestamp else None,
                "attendees": attendees,
                "topics": topics,
                "tasks": tasks,
                "projects": projects
            }
    
    async def get_meetings_for_member(self, member_name: str) -> Dict[str, Any]:
        """Get all meetings a member attended."""
        await self._ensure_cache()
        
        matched = self._fuzzy_match_member(member_name)
        if not matched:
            return {"error": f"Could not find a member matching '{member_name}'"}
        
        async with self.async_session() as session:
            result = await session.execute(
                select(Meeting)
                .join(MeetingMembers, Meeting.meeting_id == MeetingMembers.meeting_id)
                .where(MeetingMembers.member_id == matched['id'])
                .order_by(Meeting.ingestion_timestamp.desc())
            )
            
            meetings = []
            for meeting in result.scalars():
                meetings.append({
                    'meeting_id': meeting.meeting_id,
                    'name': meeting.meeting_name,
                    'type': meeting.meeting_type,
                    'date': str(meeting.ingestion_timestamp.date()) if meeting.ingestion_timestamp else None
                })
            
            return {
                "message": f"Found {len(meetings)} meeting(s) for {matched['name']}",
                "meetings": meetings
            }
    
    async def get_missed_meetings(self, discord_id: int) -> Dict[str, Any]:
        """Get meetings the user did NOT attend."""
        member = await self.get_member_by_discord_id(discord_id)
        if not member:
            return {"error": "Could not find your member record."}
        
        async with self.async_session() as session:
            # Get all meetings
            all_meetings_result = await session.execute(
                select(Meeting).order_by(Meeting.ingestion_timestamp.desc())
            )
            all_meetings = {m.meeting_id: m for m in all_meetings_result.scalars()}
            
            # Get meetings user attended
            attended_result = await session.execute(
                select(MeetingMembers.meeting_id)
                .where(MeetingMembers.member_id == member['id'])
            )
            attended_ids = {r[0] for r in attended_result.fetchall()}
            
            # Find missed meetings
            missed = []
            for meeting_id, meeting in all_meetings.items():
                if meeting_id not in attended_ids:
                    # Get topics for this meeting
                    topics_result = await session.execute(
                        select(Topic.topic_name)
                        .join(MeetingTopics, Topic.topic_id == MeetingTopics.topic_id)
                        .where(MeetingTopics.meeting_id == meeting_id)
                    )
                    topics = [t[0] for t in topics_result.fetchall()]
                    
                    missed.append({
                        'meeting_id': meeting.meeting_id,
                        'name': meeting.meeting_name,
                        'type': meeting.meeting_type,
                        'date': str(meeting.ingestion_timestamp.date()) if meeting.ingestion_timestamp else None,
                        'summary': meeting.meeting_summary[:200] + "..." if meeting.meeting_summary and len(meeting.meeting_summary) > 200 else meeting.meeting_summary,
                        'topics': topics
                    })
            
            if not missed:
                return {"message": f"You ({member['name']}) have attended all meetings!", "missed_meetings": []}
            
            return {
                "message": f"You missed {len(missed)} meeting(s)",
                "missed_meetings": missed
            }
    
    async def get_project_info(self, project_name: str) -> Dict[str, Any]:
        """Get detailed info about a project."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Project).where(
                    Project.project_name.ilike(f"%{project_name}%")
                )
            )
            projects = result.scalars().all()
            
            if not projects:
                return {"error": f"Could not find a project matching '{project_name}'"}
            
            if len(projects) > 1:
                # Try exact match
                for p in projects:
                    if p.project_name.lower() == project_name.lower():
                        projects = [p]
                        break
                else:
                    return {
                        "error": "Multiple projects match that name",
                        "matches": [{"id": p.project_id, "name": p.project_name} for p in projects[:5]]
                    }
            
            project = projects[0]
            
            # Get team members
            members_result = await session.execute(
                select(Committee.member_name, Committee.role)
                .join(ProjectMembers, Committee.member_id == ProjectMembers.member_id)
                .where(ProjectMembers.project_id == project.project_id)
            )
            members = [{"name": m[0], "role": m[1]} for m in members_result.fetchall()]
            
            # Get related tasks
            tasks_result = await session.execute(
                select(Task.task_name, Task.task_status, Task.task_deadline)
                .join(ProjectTasks, Task.task_id == ProjectTasks.task_id)
                .where(ProjectTasks.project_id == project.project_id)
            )
            tasks = [{
                "name": t[0], 
                "status": t[1] or 'incomplete',
                "deadline": str(t[2]) if t[2] else None
            } for t in tasks_result.fetchall()]
            
            return {
                "project_id": project.project_id,
                "name": project.project_name,
                "description": project.project_description,
                "team_members": members,
                "tasks": tasks
            }
    
    async def get_all_projects(self) -> Dict[str, Any]:
        """Get all projects."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Project).order_by(Project.project_name)
            )
            
            projects = []
            for project in result.scalars():
                # Get member count
                count_result = await session.execute(
                    select(func.count()).select_from(ProjectMembers)
                    .where(ProjectMembers.project_id == project.project_id)
                )
                member_count = count_result.scalar() or 0
                
                projects.append({
                    'project_id': project.project_id,
                    'name': project.project_name,
                    'description': project.project_description[:100] + "..." if project.project_description and len(project.project_description) > 100 else project.project_description,
                    'member_count': member_count
                })
            
            return {
                "message": f"Found {len(projects)} project(s)",
                "projects": projects
            }
    
    async def get_all_members(self) -> Dict[str, Any]:
        """Get all committee members."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Committee).order_by(Committee.member_name)
            )
            
            members = []
            for member in result.scalars():
                members.append({
                    'member_id': member.member_id,
                    'name': member.member_name,
                    'role': member.role,
                    'subcommittee': member.subcommittee,
                    'email': member.email
                })
            
            return {
                "message": f"Found {len(members)} member(s)",
                "members": members
            }
    
    async def get_topic_info(self, topic_name: str) -> Dict[str, Any]:
        """Get info about a topic."""
        async with self.async_session() as session:
            result = await session.execute(
                select(Topic).where(
                    Topic.topic_name.ilike(f"%{topic_name}%")
                )
            )
            topics = result.scalars().all()
            
            if not topics:
                return {"error": f"Could not find a topic matching '{topic_name}'"}
            
            topic = topics[0]  # Take first match
            
            # Get meetings that discussed this topic
            meetings_result = await session.execute(
                select(Meeting.meeting_name, Meeting.meeting_type)
                .join(MeetingTopics, Meeting.meeting_id == MeetingTopics.meeting_id)
                .where(MeetingTopics.topic_id == topic.topic_id)
            )
            meetings = [{"name": m[0], "type": m[1]} for m in meetings_result.fetchall()]
            
            return {
                "topic_id": topic.topic_id,
                "name": topic.topic_name,
                "description": topic.topic_description,
                "discussed_in_meetings": meetings
            }
    
    async def search_database(self, search_query: str, search_in: str = "all") -> Dict[str, Any]:
        """General search across the database."""
        results = {}
        query_lower = search_query.lower()
        
        async with self.async_session() as session:
            if search_in in ["members", "all"]:
                result = await session.execute(
                    select(Committee).where(
                        or_(
                            Committee.member_name.ilike(f"%{search_query}%"),
                            Committee.email.ilike(f"%{search_query}%"),
                            Committee.role.ilike(f"%{search_query}%")
                        )
                    ).limit(10)
                )
                members = [{"name": m.member_name, "role": m.role, "email": m.email} for m in result.scalars()]
                if members:
                    results["members"] = members
            
            if search_in in ["meetings", "all"]:
                result = await session.execute(
                    select(Meeting).where(
                        or_(
                            Meeting.meeting_name.ilike(f"%{search_query}%"),
                            Meeting.meeting_summary.ilike(f"%{search_query}%")
                        )
                    ).limit(10)
                )
                meetings = [{"name": m.meeting_name, "type": m.meeting_type} for m in result.scalars()]
                if meetings:
                    results["meetings"] = meetings
            
            if search_in in ["projects", "all"]:
                result = await session.execute(
                    select(Project).where(
                        or_(
                            Project.project_name.ilike(f"%{search_query}%"),
                            Project.project_description.ilike(f"%{search_query}%")
                        )
                    ).limit(10)
                )
                projects = [{"name": p.project_name, "description": p.project_description[:100] if p.project_description else None} for p in result.scalars()]
                if projects:
                    results["projects"] = projects
            
            if search_in in ["tasks", "all"]:
                result = await session.execute(
                    select(Task).where(
                        or_(
                            Task.task_name.ilike(f"%{search_query}%"),
                            Task.task_description.ilike(f"%{search_query}%")
                        )
                    ).limit(10)
                )
                tasks = [{"name": t.task_name, "status": t.task_status or 'incomplete'} for t in result.scalars()]
                if tasks:
                    results["tasks"] = tasks
            
            if search_in in ["topics", "all"]:
                result = await session.execute(
                    select(Topic).where(
                        or_(
                            Topic.topic_name.ilike(f"%{search_query}%"),
                            Topic.topic_description.ilike(f"%{search_query}%")
                        )
                    ).limit(10)
                )
                topics = [{"name": t.topic_name} for t in result.scalars()]
                if topics:
                    results["topics"] = topics
        
        if not results:
            return {"message": f"No results found for '{search_query}'"}
        
        return {"message": f"Search results for '{search_query}'", "results": results}
    
    # -------------------- EDIT FUNCTIONS --------------------
    
    async def update_task_status(self, task_identifier: str, new_status: str) -> Dict[str, Any]:
        """Update a task's status."""
        if new_status not in ['complete', 'incomplete']:
            return {"error": "Status must be 'complete' or 'incomplete'"}
        
        async with self.async_session() as session:
            # Find the task
            task = None
            try:
                task_id = int(task_identifier)
                result = await session.execute(
                    select(Task).where(Task.task_id == task_id)
                )
                task = result.scalar_one_or_none()
            except ValueError:
                pass
            
            if not task:
                result = await session.execute(
                    select(Task).where(
                        Task.task_name.ilike(f"%{task_identifier}%")
                    )
                )
                tasks = result.scalars().all()
                if len(tasks) == 1:
                    task = tasks[0]
                elif len(tasks) > 1:
                    return {
                        "error": "Multiple tasks match that name. Please be more specific.",
                        "matches": [{"id": t.task_id, "name": t.task_name} for t in tasks[:5]]
                    }
            
            if not task:
                return {"error": f"Could not find a task matching '{task_identifier}'"}
            
            old_status = task.task_status or 'incomplete'
            task.task_status = new_status
            await session.commit()
            
            return {
                "success": True,
                "message": f"Task '{task.task_name}' status updated from '{old_status}' to '{new_status}'",
                "task_id": task.task_id,
                "task_name": task.task_name,
                "old_status": old_status,
                "new_status": new_status
            }
    
    async def assign_member_to_task(self, task_identifier: str, member_name: str) -> Dict[str, Any]:
        """Assign a member to a task."""
        await self._ensure_cache()
        
        # Find member
        matched_member = self._fuzzy_match_member(member_name)
        if not matched_member:
            return {"error": f"Could not find a member matching '{member_name}'"}
        
        async with self.async_session() as session:
            # Find the task
            task = None
            try:
                task_id = int(task_identifier)
                result = await session.execute(
                    select(Task).where(Task.task_id == task_id)
                )
                task = result.scalar_one_or_none()
            except ValueError:
                pass
            
            if not task:
                result = await session.execute(
                    select(Task).where(
                        Task.task_name.ilike(f"%{task_identifier}%")
                    )
                )
                tasks = result.scalars().all()
                if len(tasks) == 1:
                    task = tasks[0]
                elif len(tasks) > 1:
                    return {
                        "error": "Multiple tasks match. Please be more specific.",
                        "matches": [{"id": t.task_id, "name": t.task_name} for t in tasks[:5]]
                    }
            
            if not task:
                return {"error": f"Could not find a task matching '{task_identifier}'"}
            
            # Check if already assigned
            existing = await session.execute(
                select(TaskMembers).where(
                    and_(
                        TaskMembers.task_id == task.task_id,
                        TaskMembers.member_id == matched_member['id']
                    )
                )
            )
            if existing.scalar_one_or_none():
                return {"error": f"{matched_member['name']} is already assigned to '{task.task_name}'"}
            
            # Create assignment
            session.add(TaskMembers(
                task_id=task.task_id,
                member_id=matched_member['id']
            ))
            await session.commit()
            
            return {
                "success": True,
                "message": f"Assigned {matched_member['name']} to task '{task.task_name}'",
                "task_id": task.task_id,
                "task_name": task.task_name,
                "member_name": matched_member['name']
            }
    
    async def remove_member_from_task(self, task_identifier: str, member_name: str) -> Dict[str, Any]:
        """Remove a member from a task."""
        await self._ensure_cache()
        
        matched_member = self._fuzzy_match_member(member_name)
        if not matched_member:
            return {"error": f"Could not find a member matching '{member_name}'"}
        
        async with self.async_session() as session:
            # Find the task
            task = None
            try:
                task_id = int(task_identifier)
                result = await session.execute(
                    select(Task).where(Task.task_id == task_id)
                )
                task = result.scalar_one_or_none()
            except ValueError:
                pass
            
            if not task:
                result = await session.execute(
                    select(Task).where(
                        Task.task_name.ilike(f"%{task_identifier}%")
                    )
                )
                tasks = result.scalars().all()
                if len(tasks) == 1:
                    task = tasks[0]
            
            if not task:
                return {"error": f"Could not find a task matching '{task_identifier}'"}
            
            # Delete assignment
            result = await session.execute(
                delete(TaskMembers).where(
                    and_(
                        TaskMembers.task_id == task.task_id,
                        TaskMembers.member_id == matched_member['id']
                    )
                )
            )
            await session.commit()
            
            if result.rowcount == 0:
                return {"error": f"{matched_member['name']} was not assigned to '{task.task_name}'"}
            
            return {
                "success": True,
                "message": f"Removed {matched_member['name']} from task '{task.task_name}'"
            }
    
    # -------------------- CREATE FUNCTIONS --------------------
    
    async def create_task(
        self, 
        task_name: str, 
        task_description: Optional[str] = None,
        deadline: Optional[str] = None,
        assigned_to: Optional[List[str]] = None,
        assign_to_current_user: bool = False,
        current_user_discord_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new task."""
        await self._ensure_cache()
        
        # Parse deadline
        task_deadline = None
        if deadline and deadline.lower() != 'null':
            try:
                task_deadline = datetime.strptime(deadline, '%Y-%m-%d').date()
            except ValueError:
                return {"error": f"Invalid deadline format. Please use YYYY-MM-DD"}
        
        # Match assigned members from explicit names
        matched_members: List[Dict[str, Any]] = []
        if assigned_to:
            for name in assigned_to:
                matched = self._fuzzy_match_member(name)
                if matched:
                    matched_members.append(matched)
                else:
                    return {"error": f"Could not find a member matching '{name}'"}
        
        # Optionally also assign the current Discord user
        if assign_to_current_user and current_user_discord_id is not None:
            current_member = await self.get_member_by_discord_id(current_user_discord_id)
            if not current_member:
                return {"error": "Could not find your member record to assign this task. Please contact an admin to link your Discord account."}
            # Avoid duplicates if their name was also in assigned_to
            if not any(m["id"] == current_member["id"] for m in matched_members):
                matched_members.append(current_member)
        
        async with self.async_session() as session:
            # Create task
            new_task = Task(
                task_name=task_name,
                task_description=task_description,
                task_deadline=task_deadline,
                task_status='incomplete'
            )
            session.add(new_task)
            await session.flush()
            
            # Assign members
            for member in matched_members:
                session.add(TaskMembers(
                    task_id=new_task.task_id,
                    member_id=member['id']
                ))
            
            await session.commit()
            
            return {
                "success": True,
                "message": f"Created task '{task_name}'" + (f" and assigned to {', '.join(m['name'] for m in matched_members)}" if matched_members else ""),
                "task_id": new_task.task_id,
                "task_name": task_name,
                "deadline": str(task_deadline) if task_deadline else None,
                "assigned_to": [m['name'] for m in matched_members]
            }
    
    async def create_project(
        self,
        project_name: str,
        project_description: Optional[str] = None,
        team_members: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a new project."""
        await self._ensure_cache()
        
        # Match team members
        matched_members = []
        if team_members:
            for name in team_members:
                matched = self._fuzzy_match_member(name)
                if matched:
                    matched_members.append(matched)
                else:
                    return {"error": f"Could not find a member matching '{name}'"}
        
        async with self.async_session() as session:
            # Check if project already exists
            existing = await session.execute(
                select(Project).where(Project.project_name.ilike(project_name))
            )
            if existing.scalar_one_or_none():
                return {"error": f"A project named '{project_name}' already exists"}
            
            # Create project
            new_project = Project(
                project_name=project_name,
                project_description=project_description
            )
            session.add(new_project)
            await session.flush()
            
            # Add members
            for member in matched_members:
                session.add(ProjectMembers(
                    project_id=new_project.project_id,
                    member_id=member['id']
                ))
            
            await session.commit()
            
            return {
                "success": True,
                "message": f"Created project '{project_name}'" + (f" with team: {', '.join(m['name'] for m in matched_members)}" if matched_members else ""),
                "project_id": new_project.project_id,
                "project_name": project_name,
                "team_members": [m['name'] for m in matched_members]
            }
    
    async def add_member_to_project(self, project_name: str, member_name: str) -> Dict[str, Any]:
        """Add a member to an existing project."""
        await self._ensure_cache()
        
        matched_member = self._fuzzy_match_member(member_name)
        if not matched_member:
            return {"error": f"Could not find a member matching '{member_name}'"}
        
        async with self.async_session() as session:
            # Find project
            result = await session.execute(
                select(Project).where(
                    Project.project_name.ilike(f"%{project_name}%")
                )
            )
            projects = result.scalars().all()
            
            if not projects:
                return {"error": f"Could not find a project matching '{project_name}'"}
            
            if len(projects) > 1:
                return {
                    "error": "Multiple projects match. Please be more specific.",
                    "matches": [p.project_name for p in projects[:5]]
                }
            
            project = projects[0]
            
            # Check if already a member
            existing = await session.execute(
                select(ProjectMembers).where(
                    and_(
                        ProjectMembers.project_id == project.project_id,
                        ProjectMembers.member_id == matched_member['id']
                    )
                )
            )
            if existing.scalar_one_or_none():
                return {"error": f"{matched_member['name']} is already a member of '{project.project_name}'"}
            
            # Add member
            session.add(ProjectMembers(
                project_id=project.project_id,
                member_id=matched_member['id']
            ))
            await session.commit()
            
            return {
                "success": True,
                "message": f"Added {matched_member['name']} to project '{project.project_name}'"
            }
    
    async def create_topic(
        self,
        topic_name: str,
        topic_description: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new topic."""
        async with self.async_session() as session:
            # Check if topic already exists
            existing = await session.execute(
                select(Topic).where(Topic.topic_name.ilike(topic_name))
            )
            if existing.scalar_one_or_none():
                return {"error": f"A topic named '{topic_name}' already exists"}
            
            new_topic = Topic(
                topic_name=topic_name,
                topic_description=topic_description
            )
            session.add(new_topic)
            await session.commit()
            
            return {
                "success": True,
                "message": f"Created topic '{topic_name}'",
                "topic_id": new_topic.topic_id,
                "topic_name": topic_name
            }
    
    async def add_topic_to_meeting(self, meeting_identifier: str, topic_name: str) -> Dict[str, Any]:
        """Link a topic to a meeting."""
        async with self.async_session() as session:
            # Find meeting
            meeting = None
            try:
                meeting_id = int(meeting_identifier)
                result = await session.execute(
                    select(Meeting).where(Meeting.meeting_id == meeting_id)
                )
                meeting = result.scalar_one_or_none()
            except ValueError:
                pass
            
            if not meeting:
                result = await session.execute(
                    select(Meeting).where(
                        Meeting.meeting_name.ilike(f"%{meeting_identifier}%")
                    )
                )
                meetings = result.scalars().all()
                if len(meetings) == 1:
                    meeting = meetings[0]
                elif len(meetings) > 1:
                    return {
                        "error": "Multiple meetings match. Please be more specific.",
                        "matches": [m.meeting_name for m in meetings[:5]]
                    }
            
            if not meeting:
                return {"error": f"Could not find a meeting matching '{meeting_identifier}'"}
            
            # Find or create topic
            topic_result = await session.execute(
                select(Topic).where(Topic.topic_name.ilike(f"%{topic_name}%"))
            )
            topic = topic_result.scalar_one_or_none()
            
            if not topic:
                # Create new topic
                topic = Topic(topic_name=topic_name)
                session.add(topic)
                await session.flush()
            
            # Check if already linked
            existing = await session.execute(
                select(MeetingTopics).where(
                    and_(
                        MeetingTopics.meeting_id == meeting.meeting_id,
                        MeetingTopics.topic_id == topic.topic_id
                    )
                )
            )
            if existing.scalar_one_or_none():
                return {"error": f"Topic '{topic.topic_name}' is already linked to meeting '{meeting.meeting_name}'"}
            
            # Link topic to meeting
            session.add(MeetingTopics(
                meeting_id=meeting.meeting_id,
                topic_id=topic.topic_id
            ))
            await session.commit()
            
            return {
                "success": True,
                "message": f"Linked topic '{topic.topic_name}' to meeting '{meeting.meeting_name}'"
            }
    
    async def close(self):
        """Close database connections."""
        await self.engine.dispose()


# ============================================================================
# Tool Executor
# ============================================================================

class ToolExecutor:
    """
    Executes database tools based on function calls from the LLM.
    """
    
    def __init__(self):
        self.db_tools = DatabaseTools()
    
    async def execute(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any],
        user_discord_id: Optional[int] = None
    ) -> str:
        """
        Execute a tool and return the result as a JSON string.
        
        Args:
            tool_name: Name of the tool/function to call
            arguments: Arguments for the function
            user_discord_id: Discord ID of the user making the request
        """
        try:
            result = await self._call_tool(tool_name, arguments, user_discord_id)
            return json.dumps(result, indent=2, default=str)
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            return json.dumps({"error": f"Tool execution failed: {str(e)}"})
    
    async def _call_tool(
        self, 
        tool_name: str, 
        args: Dict[str, Any],
        user_discord_id: Optional[int]
    ) -> Dict[str, Any]:
        """Route to the appropriate tool function."""
        
        # RETRIEVAL
        if tool_name == "get_my_tasks":
            if not user_discord_id:
                return {"error": "Cannot identify you. Your Discord account may not be linked."}
            return await self.db_tools.get_my_tasks(user_discord_id)
        
        elif tool_name == "get_my_identity":
            if not user_discord_id:
                return {"error": "Cannot identify you. Your Discord account may not be linked."}
            return await self.db_tools.get_my_identity(user_discord_id)
        
        elif tool_name == "get_current_datetime":
            # This tool does not touch the database; just returns server time.
            now = datetime.now()
            return {
                "current_datetime_iso": now.isoformat(),
                "current_date": now.date().isoformat(),
                "current_time": now.time().strftime("%H:%M:%S"),
                "timezone": "server-local",
            }
        
        elif tool_name == "get_all_tasks":
            return await self.db_tools.get_all_tasks(args.get("status_filter", "all"))
        
        elif tool_name == "get_member_info":
            return await self.db_tools.get_member_info(args["member_name"])
        
        elif tool_name == "get_meeting_info":
            return await self.db_tools.get_meeting_info(args["meeting_identifier"])
        
        elif tool_name == "get_meetings_for_member":
            return await self.db_tools.get_meetings_for_member(args["member_name"])
        
        elif tool_name == "get_missed_meetings":
            if not user_discord_id:
                return {"error": "Cannot identify you. Your Discord account may not be linked."}
            return await self.db_tools.get_missed_meetings(user_discord_id)
        
        elif tool_name == "get_project_info":
            return await self.db_tools.get_project_info(args["project_name"])
        
        elif tool_name == "get_all_projects":
            return await self.db_tools.get_all_projects()
        
        elif tool_name == "get_all_members":
            return await self.db_tools.get_all_members()
        
        elif tool_name == "get_topic_info":
            return await self.db_tools.get_topic_info(args["topic_name"])
        
        elif tool_name == "search_database":
            return await self.db_tools.search_database(
                args["search_query"],
                args.get("search_in", "all")
            )
        
        # EDIT
        elif tool_name == "update_task_status":
            return await self.db_tools.update_task_status(
                args["task_identifier"],
                args["new_status"]
            )
        
        elif tool_name == "assign_member_to_task":
            return await self.db_tools.assign_member_to_task(
                args["task_identifier"],
                args["member_name"]
            )
        
        elif tool_name == "remove_member_from_task":
            return await self.db_tools.remove_member_from_task(
                args["task_identifier"],
                args["member_name"]
            )
        
        # CREATE
        elif tool_name == "create_task":
            return await self.db_tools.create_task(
                args["task_name"],
                args.get("task_description"),
                args.get("deadline"),
                args.get("assigned_to"),
                args.get("assign_to_current_user", False),
                user_discord_id,
            )
        
        elif tool_name == "create_project":
            return await self.db_tools.create_project(
                args["project_name"],
                args.get("project_description"),
                args.get("team_members")
            )
        
        elif tool_name == "add_member_to_project":
            return await self.db_tools.add_member_to_project(
                args["project_name"],
                args["member_name"]
            )
        
        elif tool_name == "create_topic":
            return await self.db_tools.create_topic(
                args["topic_name"],
                args.get("topic_description")
            )
        
        elif tool_name == "add_topic_to_meeting":
            return await self.db_tools.add_topic_to_meeting(
                args["meeting_identifier"],
                args["topic_name"]
            )
        
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    
    async def close(self):
        """Close resources."""
        await self.db_tools.close()
