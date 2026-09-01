"""Consumer group bootstrap and existence checks (LLD §3.3)."""

# DISTRIBUTED-SYSTEMS SHOWCASE: Consumer groups — enable horizontal scaling of worker
# processes while Redis tracks pending deliveries per consumer for redelivery.

from __future__ import annotations

import redis
from redis.exceptions import ResponseError

from .errors import ConsumerGroupError
from .messages import consumer_group_message


class ConsumerGroupManager:
    def __init__(self, redis_client: redis.Redis) -> None:
        self._client = redis_client

    def ensure_group(
        self,
        stream: str,
        group: str,
        *,
        start_id: str = "0",
    ) -> None:
        try:
            self._client.xgroup_create(stream, group, id=start_id, mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                return
            raise ConsumerGroupError(
                consumer_group_message(
                    stream=stream,
                    group=group,
                    reason=str(exc),
                ),
                stream=stream,
                group=group,
            ) from exc

    def group_exists(self, stream: str, group: str) -> bool:
        try:
            groups = self._client.xinfo_groups(stream)
        except ResponseError:
            return False

        for row in groups:
            name = row.get("name")
            if name == group:
                return True
        return False
