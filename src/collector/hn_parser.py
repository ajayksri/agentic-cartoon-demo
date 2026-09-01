"""Hacker News item JSON parsing — internal types and parser."""

from __future__ import annotations

from typing import Literal

RawObservation = dict[str, object]
"""Keys: id, title, url, by, score, descendants, time, type, deleted, ..."""


class HackerNewsParser:
    def parse_item(
        self,
        observation: RawObservation,
    ) -> tuple[RawObservation | None, Literal["story", "skip", "reject_deleted"]]:
        item_type = observation.get("type")
        if item_type != "story":
            return None, "skip"

        if observation.get("deleted") is True:
            return None, "reject_deleted"

        parsed = dict(observation)
        if "id" in parsed:
            parsed["id"] = parsed["id"]

        return parsed, "story"

    def source_id_from_pool_id(self, pool_id: int) -> str:
        return str(pool_id)
