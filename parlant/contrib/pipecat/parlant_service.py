# Copyright 2025 Emcie Co Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import random
from typing import Awaitable, Callable
import soundfile
import time

from loguru import logger

from parlant.client import AsyncParlantClient

from pipecat.services.ai_service import AIService
from pipecat.processors.frame_processor import FrameDirection
from pipecat.frames.frames import (
    Frame,
    TranscriptionFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    LLMFullResponseEndFrame,
    OutputAudioRawFrame,
    StartFrame,
    EndFrame,
    CancelFrame,
)


DEFAULT_GREETING = "Hi, I'm an AI assistant. Please bear with me as I may take a few seconds to process your speech. How can I help you today?"

DEFAULT_TYPING_TRACK = (
    Path(__file__).resolve().parent / "assets" / "typing.wav"
).as_posix()

DEFAULT_TIME_TO_WAIT_BETWEEN_TYPING_AND_FILLER_PHRASE = 3.0


@dataclass(frozen=True)
class ParlantConfig:
    agent_id: str | None = field(default=None)
    """ The ID of the Palrant agent to connect to. Defaults to the first agent. """

    customer_id_provider: Callable[[], Awaitable[str | None]] | None = field(
        default=None
    )
    """ A function to get the ID of the Palrant customer to use in the session. Defaults to the guest customer if not provided. """

    url: str = field(default="http://localhost:8800")
    """ The base URL of the Parlant server. """

    client: AsyncParlantClient | None = field(default=None)
    """ An optional pre-configured Parlant client. If provided, `url` is ignored. """


@dataclass(frozen=True)
class TypingTrackConfig:
    use_typing_track: bool = field(default=True)
    """ Whether to use typing sound effects when the agent is "typing". """

    typing_track_filename: str = field(default=DEFAULT_TYPING_TRACK)
    """ The filename of the typing sound effect. Must be a mono (1-channel) WAV file. """

    typing_track_sample_rate: int = field(default=16000)
    """ The sample rate of the typing sound effect."""


@dataclass
class FillerPhraseProviderParams:
    session_id: str
    agent_id: str
    customer_id: str | None
    last_agent_message: str | None
    last_customer_message: str | None


async def default_filler_phrase_provider(
    params: FillerPhraseProviderParams,
) -> str | None:
    return random.choice(
        [
            "Just a sec.",
            "Just one second please.",
            "Just a moment.",
            "One moment please.",
            "Give me a sec.",
        ]
    )


class ParlantService(AIService):
    def __init__(
        self,
        parlant_config: ParlantConfig = ParlantConfig(),
        agent_greeting: str | None = DEFAULT_GREETING,
        filler_phrase_provider: Callable[
            [FillerPhraseProviderParams], Awaitable[str | None]
        ] = default_filler_phrase_provider,
        typing_track_config: TypingTrackConfig = TypingTrackConfig(),
    ):
        super().__init__()

        self.agent_greeting = agent_greeting

        self._filler_phrase_provider = filler_phrase_provider
        self._parlant_config = parlant_config

        self._parlant_client = parlant_config.client or AsyncParlantClient(
            base_url=parlant_config.url,
        )

        self._typing_track_params = typing_track_config

        if self._typing_track_params.use_typing_track:
            self._setup_typing_track()

        self._default_agent_id: str | None = None
        self._last_customer_message: str | None = None

    def _setup_typing_track(self):
        audio, sr = soundfile.read(
            self._typing_track_params.typing_track_filename,
            dtype="int16",
        )

        if sr != self._typing_track_params.typing_track_sample_rate:
            raise ValueError(
                f"Typing track must be {self._typing_track_params.typing_track_sample_rate} Hz but is {sr} Hz instead"
            )

        if audio.ndim != 1:
            raise ValueError("Typing track must be mono")

        self._typing_track_bytes = audio.tobytes()
        self._typing = asyncio.Event()

    async def _get_agent_id(self) -> str:
        if self._parlant_config.agent_id:
            return self._parlant_config.agent_id

        if self._default_agent_id:
            return self._default_agent_id

        # Infer, save, and return default agent ID

        agents = await self._parlant_client.agents.list()

        if not agents:
            raise ValueError("No agents available in Parlant")

        logger.warning(
            f"No agent ID provided, defaulting to the first agent: {agents[0].name} ({agents[0].id})"
        )

        self._default_agent_id = agents[0].id

        return self._default_agent_id

    async def _start_typing_task(self) -> None:
        if not self._typing_track_params.use_typing_track:
            return

        chunk_ms = 50

        bytes_per_sample = 2
        samples_per_chunk = int(
            self._typing_track_params.typing_track_sample_rate * (chunk_ms / 1000)
        )
        step = samples_per_chunk * bytes_per_sample

        async def play_track_in_chunks_until_typing_event_is_cleared() -> None:
            for i in range(0, len(self._typing_track_bytes), step):
                if not self._typing.is_set():
                    return

                chunk = self._typing_track_bytes[i : i + step]

                # push chunk
                await self.push_frame(
                    OutputAudioRawFrame(
                        audio=chunk,
                        sample_rate=self._typing_track_params.typing_track_sample_rate,
                        num_channels=1,
                    ),
                    FrameDirection.DOWNSTREAM,
                )

                # wait for chunk to finish playing
                await asyncio.sleep(chunk_ms / 1000)

        while True:
            await self._typing.wait()
            await play_track_in_chunks_until_typing_event_is_cleared()

    def _start_typing(self) -> None:
        self._typing.set()

    def _stop_typing(self) -> None:
        self._typing.clear()

    async def _create_customer_event(self, text: str) -> None:
        await self._parlant_client.sessions.create_event(
            session_id=self._parlant_session_id,
            kind="message",
            source="customer",
            message=text,
        )

        self._last_customer_message = text

    async def _create_manual_agent_event(self, text: str) -> None:
        await self._parlant_client.sessions.create_event(
            session_id=self._parlant_session_id,
            kind="message",
            source="human_agent_on_behalf_of_ai_agent",
            message=text,
        )

    async def _speak(self, text: str) -> None:
        self._stop_typing()
        await asyncio.sleep(0.2)  # small pause before speaking

        await self.push_frame(LLMFullResponseStartFrame())
        await self.push_frame(LLMTextFrame(text))
        await self.push_frame(LLMFullResponseEndFrame())

    async def _process_agent_responses(self) -> None:
        typing_task = asyncio.create_task(self._start_typing_task())

        last_typing_initiated_at = 0.0

        last_agent_event_offset = -1
        last_agent_message: str | None = None

        try:
            while self._running:
                try:
                    events = await self._parlant_client.sessions.list_events(
                        session_id=self._parlant_session_id,
                        min_offset=last_agent_event_offset + 1,
                        kinds="message,status",
                        wait_for_data=30,
                    )
                except Exception:
                    continue

                agent_events = [
                    e
                    for e in events
                    if e.source in ["ai_agent", "human_agent_on_behalf_of_ai_agent"]
                ]

                agent_messages = (
                    len([e for e in agent_events if e.kind == "message"]) > 0
                )

                for event in agent_events:
                    last_agent_event_offset = event.offset

                    if not agent_messages:
                        if event.kind == "status":
                            if event.data["status"] in ["processing"]:  # type: ignore
                                self._start_typing()
                                last_typing_initiated_at = time.monotonic()
                            if event.data["status"] in ["typing"]:  # type: ignore
                                if (
                                    last_typing_initiated_at
                                    + DEFAULT_TIME_TO_WAIT_BETWEEN_TYPING_AND_FILLER_PHRASE
                                    < time.monotonic()
                                ):
                                    if (
                                        filler_phrase
                                        := await self._filler_phrase_provider(
                                            FillerPhraseProviderParams(
                                                session_id=self._parlant_session_id,
                                                agent_id=await self._get_agent_id(),
                                                customer_id=await self._parlant_config.customer_id_provider()
                                                if self._parlant_config.customer_id_provider
                                                else None,
                                                last_agent_message=last_agent_message,
                                                last_customer_message=self._last_customer_message,
                                            )
                                        )
                                    ):
                                        await self._speak(filler_phrase)
                                        await asyncio.sleep(1)
                    elif event.kind == "message":
                        last_agent_message = event.data["message"]  # type: ignore
                        await self._speak(last_agent_message)
        finally:
            typing_task.cancel()

            try:
                await typing_task
            except asyncio.CancelledError:
                pass

    async def _start_new_session(self) -> str:
        try:
            session = await self._parlant_client.sessions.create(
                agent_id=await self._get_agent_id(),
                customer_id=await self._parlant_config.customer_id_provider()
                if self._parlant_config.customer_id_provider
                else None,
            )

            return session.id
        except Exception as exc:
            logger.error(f"Failed to create Parlant session: {exc}")
            raise

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)

        self._parlant_session_id = await self._start_new_session()

        self._running = True

        self._agent_response_processing_task = asyncio.create_task(
            self._process_agent_responses(),
        )

        logger.info("Parlant session started")

        if self.agent_greeting:
            await self._create_manual_agent_event(self.agent_greeting)

    async def stop(self, frame: EndFrame) -> None:
        await super().stop(frame)

        self._running = False

        await self._agent_response_processing_task

        logger.info("Parlant session ended")

    async def cancel(self, frame: CancelFrame) -> None:
        await super().cancel(frame)

        self._running = False

        self._agent_response_processing_task.cancel()

        try:
            await self._agent_response_processing_task
        except asyncio.CancelledError:
            pass

        logger.info("Parlant session cancelled")

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            await self._create_customer_event(frame.text)
        else:
            await self.push_frame(frame, direction)
