"""Runtime configuration, sourced from environment variables."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast, get_args

from .voices import DEFAULT_VOICE

__all__ = ["AgentEffort", "Config", "load_config"]

logger = logging.getLogger(__name__)

# What the API will accept for how hard to think. Spelled out here so a typo in
# a systemd unit is caught on the way up, with a line in the journal, rather
# than at 2am as a 400 on the first question of the night.
AgentEffort = Literal["low", "medium", "high", "xhigh", "max"]


def _default_data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME", "~/.local/share")
    return Path(xdg).expanduser() / "somnia"


@dataclass
class Config:
    """All somnia settings.

    Nine of these are read from the environment by :func:`load_config`. The
    rest — the silence lengths, the window shape, the bitrate and the agent's
    token ceiling — are settable only in code, because changing them changes
    what a render or an index means and should not be a stray variable in a
    systemd unit.
    """

    data_dir: Path = field(default_factory=_default_data_dir)
    library_dir: Path = Path("~/library/audiobooks")
    abs_url: str = "http://127.0.0.1:13378"
    abs_token: str = ""
    abs_library_id: str = ""
    # What a render uses when the request did not say. Every submission from the
    # page names a voice; the agent's never does, and neither does a bare
    # `somnia add`. See :mod:`somnia.voices` for the roster and for why the
    # language code is derived from the name rather than set beside it.
    voice: str = DEFAULT_VOICE
    embed_model: str = "intfloat/e5-small-v2"
    # Haiku was the first choice, on cost: cents per conversation, and enough
    # to turn a mumbled description into a timestamp. It went back on that by
    # reading a character's name as the title of a book somnia does not have
    # and saying so, and Sonnet — a few cents more a night — did not.
    #
    # That reason has expired, and the evidence is worth writing down rather
    # than repeating. 85 turns per model on nuc2 (2026-08-08), against the real
    # book with 51 minutes of 306 heard, over the prompt as it stands now
    # rather than the much softer one Haiku was judged against:
    #
    #                       routing        spoiler-safe   median   p90
    #   sonnet-5 (medium)   84/85          82/85          4.89s    6.40s
    #   haiku-4.5           85/85          83/85          2.46s    3.50s
    #
    # Routing is every question that had to be answered rather than acted on,
    # every name that had to be looked for in the book rather than the catalog
    # — Rob Roy among them, five times, passed — and every request that really
    # was a move. Haiku did not reproduce the failure that demoted it.
    #
    # Neither model is clean on spoilers and the two are indistinguishable at
    # this sample size, so that column is not a reason to prefer either. It is
    # a reason to read ADR 6 again: retrieval never crossed the line in any of
    # those turns — that was checked separately, mechanically — so what leaked
    # came out of the model's own knowledge of the book, which is bounded by a
    # sentence in the prompt and nothing else.
    #
    # So the default stays Sonnet on nothing stronger than habit, and
    # SOMNIA_AGENT_MODEL=claude-haiku-4-5 costs a fifth as much and answers in
    # half the time. It is a night's use away from being the default.
    agent_model: str = "claude-sonnet-5"
    # How hard the model is allowed to think before it answers. Sonnet 5 thinks
    # by default and defaults this to "high", which is what a question at 2am
    # was waiting on: measured on nuc2, "medium" takes about two seconds off
    # every turn and answers the same way on every case there is a test for.
    #
    # Lowering it is the safe half of that trade. Turning thinking off outright
    # is faster still and is deliberately not done: on Sonnet 5 a turn with no
    # thinking can write its tool call into the reply as prose instead of
    # calling the tool, which does not fail — it comes back as a sentence about
    # a search that never ran, and at 2am that is indistinguishable from an
    # answer. Two seconds is not worth a lie.
    agent_effort: AgentEffort = "medium"
    agent_max_tokens: int = 4096
    anthropic_api_key: str = ""
    sentence_silence_ms: int = 120
    paragraph_silence_ms: int = 500
    window_sentences: int = 3
    window_stride: int = 2
    aac_bitrate: str = "64k"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "somnia.db"


def load_config() -> Config:
    cfg = Config()
    if v := os.environ.get("SOMNIA_DATA_DIR"):
        cfg.data_dir = Path(v).expanduser()
    if v := os.environ.get("SOMNIA_LIBRARY_DIR"):
        cfg.library_dir = Path(v).expanduser()
    cfg.library_dir = cfg.library_dir.expanduser()
    if v := os.environ.get("SOMNIA_ABS_URL"):
        cfg.abs_url = v.rstrip("/")
    if v := os.environ.get("SOMNIA_ABS_TOKEN"):
        cfg.abs_token = v
    if v := os.environ.get("SOMNIA_ABS_LIBRARY_ID"):
        cfg.abs_library_id = v
    if v := os.environ.get("SOMNIA_VOICE"):
        cfg.voice = v
    if v := os.environ.get("SOMNIA_EMBED_MODEL"):
        cfg.embed_model = v
    if v := os.environ.get("SOMNIA_AGENT_MODEL"):
        cfg.agent_model = v
    if v := os.environ.get("SOMNIA_AGENT_EFFORT"):
        if v in get_args(AgentEffort):
            cfg.agent_effort = cast(AgentEffort, v)
        else:
            # Kept rather than raised: an unusable effort level is not worth
            # refusing to serve the page over, and the default is a working
            # answer. It is said out loud so that "I set it to low and nothing
            # got faster" has somewhere to be looked up.
            logger.warning(
                "ignoring SOMNIA_AGENT_EFFORT=%r; expected one of %s. Using %r.",
                v,
                ", ".join(get_args(AgentEffort)),
                cfg.agent_effort,
            )
    # ANTHROPIC_API_KEY is the SDK's own variable; honour it so the key can be
    # set the way every other Anthropic tool expects.
    if v := os.environ.get("ANTHROPIC_API_KEY"):
        cfg.anthropic_api_key = v
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    return cfg
