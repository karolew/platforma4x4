from __future__ import annotations

from typing import AsyncIterator, TypeVar

import aiomqtt
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class MqttBus:
    def __init__(self, host: str, port: int = 1883, client_id: str | None = None) -> None:
        self._host = host
        self._port = port
        self._client_id = client_id
        self._client: aiomqtt.Client | None = None

    async def __aenter__(self) -> "MqttBus":
        self._client = aiomqtt.Client(self._host, self._port, identifier=self._client_id)
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._client is not None
        await self._client.__aexit__(*exc)

    async def publish(self, topic: str, message: BaseModel, qos: int = 0, retain: bool = False) -> None:
        assert self._client is not None
        await self._client.publish(topic, message.model_dump_json(), qos=qos, retain=retain)

    async def subscribe(self, topic: str, schema: type[T], qos: int = 0) -> AsyncIterator[T]:
        assert self._client is not None
        await self._client.subscribe(topic, qos=qos)
        async for msg in self._client.messages:
            if msg.topic.matches(topic):
                yield schema.model_validate_json(msg.payload)
