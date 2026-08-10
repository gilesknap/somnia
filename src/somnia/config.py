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

    Six of these are read from the environment by :func:`load_config`. The
    rest — the silence lengths, the window shape, the bitrate and the agent's
    token ceiling — are settable only in code, because changing them changes
    what a render or an index means and should not be a stray variable in a
    systemd unit.
    """

    data_dir: Path = field(default_factory=_default_data_dir)
    library_dir: Path = Path("~/library/audiobooks")
    # What a render uses when the request did not say. Every submission from the
    # page names a voice; the agent's never does, and neither does a bare
    # `somnia add`. See :mod:`somnia.voices` for the roster and for why the
    # language code is derived from the name rather than set beside it.
    voice: str = DEFAULT_VOICE
    embed_model: str = "intfloat/e5-small-v2"
    # Haiku was the first choice, on cost: cents per conversation, and enough
    # to turn a mumbled description into a timestamp. It lost the job in 9b26bb6
    # for reading a character's name as the title of a book somnia does not have
    # and saying so — the exact disambiguation the agent is here to do — and
    # Sonnet, a few cents more a night, did not.
    #
    # It has the job back, on measurement rather than on the absence of one. 85
    # turns per model on nuc2 (2026-08-08), against the real book with 51
    # minutes of 306 heard, over this prompt rather than the much softer one it
    # was judged against then:
    #
    #                       routing        spoiler-safe   median   p90
    #   sonnet-5 (medium)   84/85          82/85          4.89s    6.40s
    #   haiku-4.5           85/85          83/85          2.46s    3.50s
    #
    # Routing is every question that had to be answered rather than acted on,
    # every name that had to be looked for in the book rather than the catalog
    # — Rob Roy among them, five times — and every request that really was a
    # move. Haiku did not put a foot wrong, and did not reproduce the mistake
    # that demoted it. Half the time and a fifth of the cost, on a screen where
    # every second of the wait is felt.
    #
    # Neither model is clean on spoilers and the two are indistinguishable at
    # this sample size, so that column decided nothing. It is a reason to read
    # ADR 6 again: retrieval never crossed the line in any of those turns —
    # checked separately, mechanically — so what leaked came out of the model's
    # own knowledge of the book, bounded by a sentence in the prompt and
    # nothing else. That is true of whichever model is named here.
    #
    # Five tries at one question is not proof the old failure is gone, so if a
    # name is ever misread as a book title again, SOMNIA_AGENT_MODEL=
    # claude-sonnet-5 is the way back and this comment is the reason to take it.
    agent_model: str = "claude-haiku-4-5"
    # How hard the model is allowed to think before it answers, for the models
    # that have such a dial. Haiku has not got one, so on the default this is
    # not sent at all and changing it does nothing — see :func:`effort_for`.
    # It is what makes Sonnet bearable if the model above is ever changed back:
    # Sonnet 5 thinks by default and defaults this to "high", which is what a
    # question at 2am was waiting on. Measured on nuc2, "medium" takes about two
    # seconds off every turn and answers the same way on every case there is a
    # test for.
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
        cfg.library_dir = Path(v)
    # Once, and on the line that catches both: the default carries a ~ and so
    # may the override, and expanding the override here as well was a second
    # pass over a path that had already had one.
    cfg.library_dir = cfg.library_dir.expanduser()
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
