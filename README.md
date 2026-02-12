# Secretary AI

An AI-powered Discord bot and meeting transcript integration system for business information management.

## Features

- **Meeting Transcript Processing**: Automatically extract participants, projects, topics, tasks, and generate summaries from meeting transcripts using GPT-4.1-mini.
- **Task Extraction**: Detect and record explicitly assigned tasks with deadlines and assignees, linked back to meetings and members.
- **Fuzzy Matching**: Intelligently match extracted names to existing database records (supports full names, unique first names, and strips a bit of extra “noisy” text).
- **File Watcher**: Monitor a landing folder for new transcripts with an interactive renaming and routing flow.
- **Discord Chatbot**: Talk to Secretary AI in Discord to retrieve information (“What are my tasks?”, “Who is Sam Choong?”, “What did I miss?”) and perform allowed updates/creations.
- **Agentic Tool Use**: The chatbot decides which database tools to call, runs them, and answers based strictly on those results (no raw SQL from the model).
- **Async Architecture**: Built for performance with async database operations and API calls.

## Quick Start

### 1. Install Dependencies

You can use either `pip` or `uv`. If you’re using `uv`, prefer running your app via `uv run` so it uses the right environment.

```bash
# Using pip + venv (recommended)
python -m venv .venv
.venv\Scripts\activate  # on Windows
pip install -r requirements.txt

# Or using uv
uv pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required environment variables:
- `DISCORD_TOKEN` - Your Discord bot token
- `OPENAI_API_KEY` - Your OpenAI API key
- `DATABASE_URL` - PostgreSQL connection string

### 3. Run the Bot

```bash
# Start Discord bot
python main.py bot
# or with uv
uv run python main.py bot

# Start file watcher
python main.py watch
# or with uv
uv run python main.py watch

# Process a file directly
python main.py process landing/my_transcript.txt
```

## Commands

### CLI Commands

```bash
python main.py bot          # Start the Discord bot
python main.py watch        # Start the file watcher
python main.py process FILE # Process a specific transcript
python main.py setup        # Create/verify database tables
python main.py help         # Show help
```

### Discord Chat Usage

- Mention the bot to chat: `@SecretaryAI ...`
- Example queries:
  - `@SecretaryAI what are my current tasks?`
  - `@SecretaryAI what did I miss in the last full committee meeting?`
  - `@SecretaryAI who is Michael Huang?`
  - `@SecretaryAI create a new task to review recruitment email copy, due next Friday, and assign it to me.`
  - `@SecretaryAI add a project called "O-Week Preparation" and assign it to all executives.`
  - `@SecretaryAI what time is it right now?`

## Project Structure

```
secretary-ai/
├── main.py                    # Main entry point
├── discord_bot/
│   └── bot.py                 # Discord bot and chat logic
├── transcript_integrator/
│   ├── __init__.py
│   ├── integrator.py          # Main transcript processing engine
│   ├── models.py              # SQLAlchemy database models
│   ├── database_tools.py      # Async database tools used by the chatbot
│   └── file_watcher.py        # File monitoring and renaming
├── landing/                   # Drop transcript files here
│   ├── executive/
│   ├── projects_subcommittee/
│   ├── events_subcommittee/
│   ├── sponsorships_subcommittee/
│   ├── marketing_subcommittee/
│   ├── content-creation_subcommittee/
│   ├── hr_subcommittee/
│   ├── full/
│   └── unscheduled/
├── database-erd.txt           # Database schema reference
├── requirements.txt
├── pyproject.toml
└── .env                       # Environment configuration
```

## Database Schema

The system uses the following tables:

| Table | Description |
|-------|-------------|
| `committee` | Organization members with Discord IDs and roles |
| `meeting` | Meeting records with summaries |
| `meeting_members` | Links meetings to attendees |
| `meeting_projects` | Links meetings to discussed projects |
| `meeting_topics` | Links meetings to discussion topics |
| `meeting_tasks` | Links meetings to assigned tasks |
| `projects` | Project information |
| `project_members` | Links projects to team members |
| `tasks` | Task records with deadlines |
| `task_members` | Links tasks to assignees |
| `topic` | Discussion topics |

## Meeting Types

The system supports the following meeting types:

- `executive` - Executive Committee Meeting
- `projects_subcommittee` - Projects Subcommittee Meeting
- `events_subcommittee` - Events Subcommittee Meeting
- `sponsorships_subcommittee` - Sponsorships Subcommittee Meeting
- `marketing_subcommittee` - Marketing Subcommittee Meeting
- `content-creation_subcommittee` - Content Creation Subcommittee Meeting
- `hr_subcommittee` - HR Subcommittee Meeting
- `full` - Full Committee Meeting
- `unscheduled` - Unscheduled / Ad-hoc Meeting

## How It Works

### File Watcher Flow

1. Drop a transcript file (`.txt`) into the `landing/` folder
2. The watcher detects the new file and prompts you:
   - Select meeting type
   - Enter meeting date (DD-MM-YYYY)
   - Enter meeting name
   - Choose destination subfolder
3. File is renamed with `INGESTED_` prefix and moved to the selected folder
4. Optionally run AI analysis to extract meeting information

### Transcript Processing

1. **Member Extraction**: Identifies participants from the transcript and matches them to committee members using fuzzy matching over full names and first names.
2. **Project Linking**: Detects project mentions and links them to the meeting.
3. **Topic Identification**: Extracts discussion topics, linking to existing topics or creating new ones if needed.
4. **Task Detection**: Finds explicitly assigned tasks with deadlines and assignees (multiple assignees become multiple `task_members` rows).
5. **Summary Generation**: Creates a comprehensive meeting summary.

### Fuzzy Matching

The system uses Python's `difflib.get_close_matches()` to handle:
- Typos and misspellings
- Name variations (plural/singular)
- Case differences

Default cutoffs:
- Members: 70% similarity
- Projects: 60% similarity
- Topics: 70% similarity

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_TOKEN` | Yes | - | Discord bot token |
| `OPENAI_API_KEY` | Yes | - | OpenAI API key |
| `DATABASE_URL` | Yes | - | PostgreSQL connection URL |
| `OPENAI_MODEL` | No | `gpt-4.1-mini` | OpenAI model to use |
| `DISCORD_PROXY` | No | - | Proxy for Discord connection |

### Example .env

```env
DISCORD_TOKEN=your_discord_token_here
DATABASE_URL=postgresql://user:password@host:5432/database
OPENAI_API_KEY=sk-your-openai-key-here
OPENAI_MODEL=gpt-4.1-mini
# DISCORD_PROXY=socks5://127.0.0.1:7898
```

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
# Using black
black .

# Using ruff
ruff check --fix .
```

## Troubleshooting

### "No match found for member: X"

The member name in the transcript doesn't closely match any names in the `committee` table. Either:
- Add the member to the database
- Use a name that more closely matches existing records

### "asyncpg.exceptions.UndefinedTableError"

The database tables don't exist. Run:

```bash
python main.py setup
```

### "duplicate key value violates unique constraint ..._pkey"

If you see an error like:

```text
duplicate key value violates unique constraint "tasks_pkey"
Key (task_id)=(1) already exists.
```

the PostgreSQL identity/sequence for that table is out of sync with existing data. You can fix it by resetting the sequence to `MAX(id) + 1`, for example:

```sql
SELECT setval(
  pg_get_serial_sequence('public.tasks', 'task_id'),
  COALESCE((SELECT MAX(task_id) FROM public.tasks), 0) + 1,
  false
);
```

Repeat with the appropriate table/column (e.g. `public.topic` / `topic_id`, `public.meeting` / `meeting_id`) if you see similar errors there.

### Discord bot not responding

1. Check that `DISCORD_TOKEN` is set correctly
2. Ensure the bot has been invited to your server with proper permissions
3. Enable "Message Content Intent" in Discord Developer Portal
4. If behind a firewall, set `DISCORD_PROXY`

## License

MIT License
