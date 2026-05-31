"""
Garmin Connect MCP Server
Exposes Garmin health & activity data as tools for Claude.
"""

import asyncio
import json
import logging
from datetime import date, timedelta
from typing import Any

from garminconnect import Garmin, GarminConnectAuthenticationError
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("garmin-mcp")

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_client(email: str, password: str) -> Garmin:
    """Authenticate and return a Garmin client."""
    client = Garmin(email, password)
    client.login()
    return client


def _today() -> str:
    return date.today().isoformat()



# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def get_steps(client: Garmin, query_date: str | None = None) -> dict:
    query_date = query_date or _today()
    data = client.get_steps_data(query_date)
    total = sum(s.get("steps", 0) for s in data) if isinstance(data, list) else data
    active_periods = [s for s in data if isinstance(data, list) and s.get("steps", 0) > 0]
    return {
        "date": query_date,
        "total_steps": total,
        "summary": f"{total:,} steps on {query_date}",
        "active_periods": len(active_periods),
        "note": "Timestamps are in GMT. Munich is UTC+2 so the day starts at 22:00 GMT the previous calendar day.",
    }


def get_sleep(client: Garmin, query_date: str | None = None) -> dict:
    query_date = query_date or _today()
    data = client.get_sleep_data(query_date)
    summary = data.get("dailySleepDTO", {}) if isinstance(data, dict) else {}
    return {
        "date": query_date,
        "duration_seconds": summary.get("sleepTimeSeconds"),
        "deep_seconds": summary.get("deepSleepSeconds"),
        "light_seconds": summary.get("lightSleepSeconds"),
        "rem_seconds": summary.get("remSleepSeconds"),
        "awake_seconds": summary.get("awakeSleepSeconds"),
        "score": summary.get("sleepScores", {}).get("overall", {}).get("value"),
        "raw": summary,
    }


def get_heart_rate(client: Garmin, query_date: str | None = None) -> dict:
    query_date = query_date or _today()
    data = client.get_heart_rates(query_date)
    return {
        "date": query_date,
        "resting_hr": data.get("restingHeartRate"),
        "max_hr": data.get("maxHeartRate"),
        "min_hr": data.get("minHeartRate"),
    }


def get_body_battery(client: Garmin, query_date: str | None = None) -> dict:
    query_date = query_date or _today()
    data = client.get_body_battery(query_date)
    if isinstance(data, list) and data:
        latest = data[-1]
        return {
            "date": query_date,
            "current": latest.get("value"),
            "charged": max((d.get("value", 0) for d in data), default=None),
            "drained": min((d.get("value", 0) for d in data), default=None),
        }
    return {"date": query_date, "data": data}


def get_stress(client: Garmin, query_date: str | None = None) -> dict:
    query_date = query_date or _today()
    data = client.get_stress_data(query_date)
    summary = data.get("stressSummary", {}) if isinstance(data, dict) else {}
    return {
        "date": query_date,
        "avg_stress": summary.get("avgStressLevel"),
        "max_stress": summary.get("maxStressLevel"),
        "rest_duration": summary.get("restStressDuration"),
        "low_duration": summary.get("lowStressDuration"),
        "medium_duration": summary.get("mediumStressDuration"),
        "high_duration": summary.get("highStressDuration"),
    }


def get_activities(client: Garmin, limit: int = 5) -> list[dict]:
    activities = client.get_activities(0, limit)
    return [
        {
            "name": a.get("activityName"),
            "type": a.get("activityType", {}).get("typeKey"),
            "date": a.get("startTimeLocal"),
            "duration_seconds": a.get("duration"),
            "distance_meters": a.get("distance"),
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "calories": a.get("calories"),
            "avg_pace": a.get("averageSpeed"),
            "elevation_gain": a.get("elevationGain"),
        }
        for a in activities
    ]


def get_stats_summary(client: Garmin, query_date: str | None = None) -> dict:
    """High-level daily stats — great for a quick overview."""
    query_date = query_date or _today()
    data = client.get_stats(query_date)
    return {
        "date": query_date,
        "total_steps": data.get("totalSteps"),
        "total_distance_meters": data.get("totalDistanceMeters"),
        "active_calories": data.get("activeKilocalories"),
        "resting_calories": data.get("bmrKilocalories"),
        "floors_ascended": data.get("floorsAscended"),
        "active_minutes": data.get("highlyActiveSeconds", 0) // 60,
        "resting_hr": data.get("restingHeartRate"),
        "avg_stress": data.get("averageStressLevel"),
        "body_battery_charged": data.get("bodyBatteryChargedValue"),
        "body_battery_drained": data.get("bodyBatteryDrainedValue"),
    }


def get_hrv(client: Garmin, query_date: str | None = None) -> dict:
    query_date = query_date or _today()
    data = client.get_hrv_data(query_date)
    summary = data.get("hrvSummary", {}) if isinstance(data, dict) else {}
    return {
        "date": query_date,
        "weekly_avg": summary.get("weeklyAvg"),
        "last_night_avg": summary.get("lastNight"),
        "last_night_5min_high": summary.get("lastNightFiveMinHigh"),
        "status": summary.get("status"),
        "feedback": summary.get("feedbackPhrase"),
    }


# ---------------------------------------------------------------------------
# MCP Server setup
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    Tool(
        name="get_stats_summary",
        description="Get a high-level daily health summary: steps, calories, HR, stress, Body Battery.",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "ISO date (YYYY-MM-DD). Defaults to today."}
            },
        },
    ),
    Tool(
        name="get_steps",
        description="Get step count for a given date.",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "ISO date (YYYY-MM-DD). Defaults to today."}
            },
        },
    ),
    Tool(
        name="get_sleep",
        description="Get sleep data including duration, stages (deep/light/REM), and sleep score.",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "ISO date (YYYY-MM-DD). Defaults to today."}
            },
        },
    ),
    Tool(
        name="get_heart_rate",
        description="Get resting, min, and max heart rate for a given date.",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "ISO date (YYYY-MM-DD). Defaults to today."}
            },
        },
    ),
    Tool(
        name="get_body_battery",
        description="Get Body Battery levels (current, charged, drained) for a given date.",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "ISO date (YYYY-MM-DD). Defaults to today."}
            },
        },
    ),
    Tool(
        name="get_stress",
        description="Get stress level summary: average, max, and time spent in each stress zone.",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "ISO date (YYYY-MM-DD). Defaults to today."}
            },
        },
    ),
    Tool(
        name="get_hrv",
        description="Get HRV (Heart Rate Variability) data including weekly average, last night average, and status.",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "ISO date (YYYY-MM-DD). Defaults to today."}
            },
        },
    ),
    Tool(
        name="get_activities",
        description="Get recent activities (runs, rides, swims, etc.) with duration, distance, HR, and calories.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of activities to return (default 5, max 20)."}
            },
        },
    ),
]


async def main(email: str, password: str) -> None:
    client = get_client(email, password)
    logger.info("Authenticated with Garmin Connect")
    app = Server("garmin-mcp")

    @app.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @app.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        try:
            match name:
                case "get_stats_summary":
                    result = get_stats_summary(client, arguments.get("date"))
                case "get_steps":
                    result = get_steps(client, arguments.get("date"))
                case "get_sleep":
                    result = get_sleep(client, arguments.get("date"))
                case "get_heart_rate":
                    result = get_heart_rate(client, arguments.get("date"))
                case "get_body_battery":
                    result = get_body_battery(client, arguments.get("date"))
                case "get_stress":
                    result = get_stress(client, arguments.get("date"))
                case "get_hrv":
                    result = get_hrv(client, arguments.get("date"))
                case "get_activities":
                    result = get_activities(client, arguments.get("limit", 5))
                case _:
                    result = {"error": f"Unknown tool: {name}"}

            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import os
    import sys

    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    if not email or not password:
        print("Set GARMIN_EMAIL and GARMIN_PASSWORD environment variables.")
        sys.exit(1)

    asyncio.run(main(email, password))