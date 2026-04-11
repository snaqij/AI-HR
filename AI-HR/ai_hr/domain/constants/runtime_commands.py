from __future__ import annotations

from enum import StrEnum


class RuntimeCommand(StrEnum):
    START_OF_SENTENCE = "start_of_sentence"
    END_OF_SENTENCE = "end_of_sentence"
    ON_CONNECTED = "on_connected"
    ON_CONNECTION_ERROR = "on_connection_error"
    ON_CONNECTION_FAILURE = "on_connection_failure"
    ON_TOKEN_EXPIRED = "on_token_expired"
    INTERRUPT = "interrupt"


class RuntimeDataChannel(StrEnum):
    TEXT_DATA = "text_data"
