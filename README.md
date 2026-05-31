# Garmin MCP Server

A Model Context Protocol server that exposes your Garmin Connect health & fitness data to Claude.

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set environment variables
```bash
export GARMIN_EMAIL="your@email.com"
export GARMIN_PASSWORD="yourpassword"
```

Or use a `.env` file with `python-dotenv`.

### 3. Test the server directly
```bash
python server.py
```

### 4. Register with Claude Code
Edit `claude_mcp_config.json` with your actual file path, then:
```bash
claude mcp add garmin python /absolute/path/to/server.py \
  --env GARMIN_EMAIL=your@email.com \
  --env GARMIN_PASSWORD=yourpassword
```

Or merge `claude_mcp_config.json` into your `~/.claude/claude_desktop_config.json`.

---

## Available Tools

| Tool | Description |
|------|-------------|
| `get_stats_summary` | Daily overview: steps, calories, HR, stress, Body Battery |
| `get_steps` | Step count for a date |
| `get_sleep` | Sleep duration, stages (deep/light/REM), score |
| `get_heart_rate` | Resting, min, max HR |
| `get_body_battery` | Body Battery charged/drained levels |
| `get_stress` | Stress level summary and time in zones |
| `get_hrv` | HRV weekly average, last night, status |
| `get_activities` | Recent activities with full stats |

All tools accept an optional `date` parameter in `YYYY-MM-DD` format. Defaults to today.

---

## Example prompts once connected

- *"How did I sleep last night?"*
- *"What's my Body Battery right now?"*
- *"Show my last 5 activities"*
- *"How has my resting HR trended this week?"*
- *"Am I recovering well based on HRV?"*

---

## Notes

- Uses the unofficial `garminconnect` Python library (reverse-engineered API)
- Works for personal use; not suitable for production/commercial apps
- Garmin occasionally changes their internal API — update `garminconnect` if things break:
  ```bash
  pip install --upgrade garminconnect
  ```
- Consider storing credentials in a secrets manager rather than plain env vars
