"""Runtime configuration, sourced from environment variables."""

import os
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Config", "load_config"]


def _default_data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME", "~/.local/share")
    return Path(xdg).expanduser() / "somnia"


@dataclass
class Config:
    """All somnia settings. Every field can be overridden via SOMNIA_* env vars."""

    data_dir: Path = field(default_factory=_default_data_dir)
    library_dir: Path = Path("~/library/audiobooks")
    abs_url: str = "http://127.0.0.1:13378"
    abs_token: str = ""
    abs_library_id: str = ""
    voice: str = "af_heart"
    embed_model: str = "intfloat/e5-small-v2"
    # Haiku was the first choice, on cost: cents per conversation, and enough
    # to turn a mumbled description into a timestamp. It went back on that by
    # reading a character's name as the title of a book somnia does not have
    # and saying so. Sonnet is a few cents more a night and does not, which is
    # the whole job. Set SOMNIA_AGENT_MODEL=claude-haiku-4-5 to go back.
    agent_model: str = "claude-sonnet-5"
    agent_max_tokens: int = 4096
    anthropic_api_key: str = ""
    # How long to wait before checking a move stuck. A player that is going to
    # report its own position back does so within a second.
    move_settle_s: float = 1.0
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
    # ANTHROPIC_API_KEY is the SDK's own variable; honour it so the key can be
    # set the way every other Anthropic tool expects.
    if v := os.environ.get("ANTHROPIC_API_KEY"):
        cfg.anthropic_api_key = v
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    return cfg
