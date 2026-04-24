#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from ten_runtime import (
    AudioFrame,
    AudioFrameDataFmt,
    AsyncExtension,
    AsyncTenEnv,
    Cmd,
    StatusCode,
    CmdResult,
    Data,
)
from .config import TENVADConfig
from ten_vad import TenVad
from enum import Enum, auto

import numpy as np
import os
import asyncio

BYTES_PER_SAMPLE = 2
SAMPLE_RATE = 16000


class VADState(Enum):
    IDLE = auto()
    SPEAKING = auto()


class TENVADPythonExtension(AsyncExtension):
    def __init__(self, name: str):
        super().__init__(name)
        self.name = name
        self.config: TENVADConfig = None
        self.hop_size: int = 0  # samples

        self.vad = None
        self.audio_buffer: bytearray = bytearray()

        # VAD state
        self.state = VADState.IDLE
        self.probe_window: list[float] = []
        self.window_size: int = 0
        self.prefix_window_size: int = 0
        self.silence_window_size: int = 0
        self.base_silence_window_size: int = 0
        self.speaking_duration_ms: float = 0

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        print("[ten_vad] on_init", flush=True)
        config_json, _ = await ten_env.get_property_to_json("")
        self.config = TENVADConfig.model_validate_json(config_json)
        ten_env.log_debug(f"config: {self.config}")

        self.hop_size = self.config.hop_size_ms * SAMPLE_RATE // 1000
        ten_env.log_debug(f"hop_size: {self.hop_size}")

        # Calculate window size based on config
        self.silence_window_size = (
            self.config.silence_duration_ms // self.config.hop_size_ms
        )
        self.prefix_window_size = (
            self.config.prefix_padding_ms // self.config.hop_size_ms
        )
        self.window_size = max(
            self.silence_window_size, self.prefix_window_size
        )
        ten_env.log_info(
            f"window_size: {self.window_size}, prefix_window_size: {self.prefix_window_size}, silence_window_size: {self.silence_window_size}"
        )
        self.base_silence_window_size = self.silence_window_size
        
        # Initialize VAD engine as early as possible
        self.vad = TenVad(self.hop_size)

    async def on_start(self, _ten_env: AsyncTenEnv) -> None:
        print("[ten_vad] on_start", flush=True)

    async def on_stop(self, _ten_env: AsyncTenEnv) -> None:
        print("[ten_vad] on_stop", flush=True)
        self.vad = None

    async def on_deinit(self, _ten_env: AsyncTenEnv) -> None:
        pass

    async def on_cmd(self, ten_env: AsyncTenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_debug("on_cmd name {}".format(cmd_name))
        cmd_result = CmdResult.create(StatusCode.OK, cmd)
        await ten_env.return_result(cmd_result)

    async def on_data(self, ten_env: AsyncTenEnv, data: Data) -> None:
        pass

    async def _check_state_transition(self, ten_env: AsyncTenEnv) -> None:
        if len(self.probe_window) < self.window_size:
            return

        if self.state == VADState.IDLE:
            # Check if we should transition to SPEAKING
            prefix_probes = self.probe_window[-self.prefix_window_size :]
            all_above_threshold = all(
                p >= self.config.vad_threshold for p in prefix_probes
            )
            if all_above_threshold:
                self.state = VADState.SPEAKING
                ten_env.log_info(f"State transition: IDLE -> SPEAKING (threshold: {self.config.vad_threshold})")

                # send start_of_sentence cmd
                await ten_env.send_cmd(Cmd.create("start_of_sentence"))
                self.speaking_duration_ms = 0

        elif self.state == VADState.SPEAKING:
            # Check if we should transition to IDLE
            silence_probes = self.probe_window[-self.silence_window_size :]
            all_below_threshold = all(
                p < self.config.vad_threshold for p in silence_probes
            )
            if all_below_threshold:
                self.state = VADState.IDLE
                ten_env.log_info("State transition: SPEAKING -> IDLE")

                # send end_of_sentence cmd
                await ten_env.send_cmd(Cmd.create("end_of_sentence"))
                
                # Reset back to baseline
                self.silence_window_size = self.base_silence_window_size
                self.window_size = max(self.silence_window_size, self.prefix_window_size)
                self.speaking_duration_ms = 0

    def _dump_audio_if_needed(self, buf: bytearray, suffix: str) -> None:
        if not self.config.dump:
            return

        dump_file = os.path.join(
            self.config.dump_path, f"{self.name}_{suffix}.pcm"
        )
        try:
            with open(dump_file, "ab") as f:
                f.write(buf)
        except:
            pass

    async def on_audio_frame(
        self, ten_env: AsyncTenEnv, audio_frame: AudioFrame
    ) -> None:
        if self.vad is None:
            return

        frame_buf = audio_frame.get_buf()
        if not frame_buf:
            return

        # self._dump_audio_if_needed(frame_buf, "in")

        # Process audio for VAD
        self.audio_buffer.extend(frame_buf)
        
        while len(self.audio_buffer) >= self.hop_size * BYTES_PER_SAMPLE:
            audio_buf = self.audio_buffer[: self.hop_size * BYTES_PER_SAMPLE]
            self.audio_buffer = self.audio_buffer[self.hop_size * BYTES_PER_SAMPLE :]

            # vad process
            probe, _flag = self.vad.process(
                np.frombuffer(audio_buf, dtype=np.int16)
            )

            # Update probe window
            self.probe_window.append(probe)
            if len(self.probe_window) > self.window_size:
                self.probe_window.pop(0)

            # Check state transition
            await self._check_state_transition(ten_env)

            # Update duration and dynamic threshold if speaking
            if self.state == VADState.SPEAKING:
                self.speaking_duration_ms += self.config.hop_size_ms
                
                # Dynamic Threshold Logic
                if self.speaking_duration_ms > 10000: # > 10s
                    target_silence_ms = 1500
                elif self.speaking_duration_ms > 3000: # > 3s
                    target_silence_ms = 1000
                else:
                    target_silence_ms = self.config.silence_duration_ms
                
                new_silence_window = target_silence_ms // self.config.hop_size_ms
                if new_silence_window != self.silence_window_size:
                    self.silence_window_size = new_silence_window
                    self.window_size = max(self.silence_window_size, self.prefix_window_size)
                    # ten_env.log_debug(f"VAD silence duration dynamically adjusted to {target_silence_ms}ms (speaking: {self.speaking_duration_ms}ms)")


if __name__ == "__main__":
    from ten_runtime import Main
    Main(TENVADPythonExtension).run()
