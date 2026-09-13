"""
live_feed.py - what the phone is doing right now, for the viz dashboard.

The phone already tells this server two things while a ride is on:
  * where the bike is, every few seconds   (POST /api/copilot/tick)
  * which assistant tools the rider's voice/typed request ran
    (POST /api/assistant, POST /api/assistant/tool)

Nothing here decides anything. It is a small in-memory record of those two
streams so a second screen can watch the same ride: the last position report
per session, and a ring of the tool calls with the ride context they were
run against and the engine's result. The dashboard polls it.
"""
from __future__ import annotations

import itertools
import threading
import time
from collections import deque
from typing import Any

MAX_EVENTS = 200
# Below this many seconds since the last tick the phone counts as "on the ride".
FRESH_S = 30.0


class LiveFeed:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seq = itertools.count(1)
        self._events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)
        self._ride: dict[str, Any] | None = None
        self._ride_at: float = 0.0

    # -- writers -----------------------------------------------------------

    def position(self, tick: dict[str, Any]) -> None:
        """One /api/copilot/tick body, kept as the phone sent it."""
        with self._lock:
            self._ride = tick
            self._ride_at = time.time()

    def tool(self, name: str, args: dict[str, Any], ride: dict[str, Any] | None,
             result: Any, source: str) -> None:
        """One assistant tool run. `args` are the model's arguments (without the
        ride context), `ride` the context it was run against, `result` what the
        engine gave back — stored whole so the dashboard draws the real plan."""
        with self._lock:
            self._events.append({
                "seq": next(self._seq), "at": time.time(), "kind": "tool",
                "source": source, "tool": name,
                "args": {k: v for k, v in args.items() if k != "_ride"},
                "ride": ride, "result": result,
            })

    def said(self, text: str, say: str, tools_used: list[str], ok: bool) -> None:
        """A typed/voice request and the sentence the assistant answered with."""
        with self._lock:
            self._events.append({
                "seq": next(self._seq), "at": time.time(), "kind": "say",
                "text": text, "say": say, "tools_used": tools_used, "ok": ok,
            })

    # -- reader ------------------------------------------------------------

    def snapshot(self, since: int = 0) -> dict[str, Any]:
        with self._lock:
            age = (time.time() - self._ride_at) if self._ride else None
            return {
                "ok": True,
                "seq": self._events[-1]["seq"] if self._events else 0,
                "ride": self._ride,
                "ride_age_s": None if age is None else round(age, 1),
                "phone_live": age is not None and age <= FRESH_S,
                "events": [e for e in self._events if e["seq"] > since],
            }
