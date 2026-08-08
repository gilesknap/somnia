"""What the environment is allowed to say, and what it means when it says it.

`load_config` is the layer everything else imports — the server, the worker, the
agent and every command line — and until this file one test touched it, for one
branch, and that test created a directory in the real home directory on its way
past. Nothing else here reaches the disk except the one line that is supposed
to: the data directory is made, because two callers rely on it being there.
"""

from pathlib import Path

import pytest

from somnia.config import Config, load_config

# Every variable the loader reads, cleared before each test so that a machine
# with SOMNIA_VOICE set in its shell does not quietly change what this suite
# proves. Named rather than wildcarded: a new variable should have to be added
# here, which is the moment somebody notices it needs a test.
VARIABLES = (
    "SOMNIA_DATA_DIR",
    "SOMNIA_LIBRARY_DIR",
    "SOMNIA_ABS_URL",
    "SOMNIA_ABS_TOKEN",
    "SOMNIA_ABS_LIBRARY_ID",
    "SOMNIA_VOICE",
    "SOMNIA_EMBED_MODEL",
    "SOMNIA_AGENT_MODEL",
    "SOMNIA_AGENT_EFFORT",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture(autouse=True)
def a_clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    # Somewhere to make the data directory that is not the real one. Every test
    # here calls the loader, and the loader makes it.
    monkeypatch.setenv("SOMNIA_DATA_DIR", str(tmp_path / "data"))


def test_the_defaults_are_the_dataclass(tmp_path: Path) -> None:
    """An empty environment is the shipped configuration, minus the one override."""
    cfg = load_config()
    plain = Config()
    assert cfg.voice == plain.voice
    assert cfg.abs_url == plain.abs_url
    assert cfg.agent_model == plain.agent_model
    assert cfg.agent_effort == plain.agent_effort
    assert cfg.embed_model == plain.embed_model


def test_the_data_directory_is_made_because_two_callers_expect_it(
    tmp_path: Path,
) -> None:
    """The one side effect the loader has, and it is load-bearing."""
    made = tmp_path / "data"
    assert not made.exists()
    cfg = load_config()
    assert cfg.data_dir == made
    assert made.is_dir()
    # And the database goes inside it, which is what the directory is for.
    assert cfg.db_path.parent == made


def test_a_tilde_is_expanded_wherever_it_comes_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default carries one and so may the override, so both are expanded.

    Once, on the line that catches both — it used to be done twice on the
    override, which was a second pass over a path that had already had one.
    """
    monkeypatch.setenv("SOMNIA_LIBRARY_DIR", "~/somewhere/else")
    assert load_config().library_dir == Path.home() / "somewhere" / "else"
    # And the default, which is where the tilde really lives.
    monkeypatch.delenv("SOMNIA_LIBRARY_DIR")
    assert "~" not in str(load_config().library_dir)
    assert load_config().library_dir.is_absolute()


def test_a_trailing_slash_on_the_abs_url_is_taken_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Because every caller appends a path to it, and // is a different route."""
    monkeypatch.setenv("SOMNIA_ABS_URL", "http://nuc2:13378/")
    assert load_config().abs_url == "http://nuc2:13378"


def test_every_plain_string_setting_comes_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One test for the settings that are read and stored and nothing else.

    Written as a table rather than five near-identical tests, because what
    would actually go wrong here is a variable read into the wrong field — and
    that is only visible when they are all set to different things at once.
    """
    monkeypatch.setenv("SOMNIA_ABS_TOKEN", "a-token")
    monkeypatch.setenv("SOMNIA_ABS_LIBRARY_ID", "lib-7")
    monkeypatch.setenv("SOMNIA_VOICE", "bm_george")
    monkeypatch.setenv("SOMNIA_EMBED_MODEL", "some/other-model")
    monkeypatch.setenv("SOMNIA_AGENT_MODEL", "claude-sonnet-5")

    cfg = load_config()

    assert cfg.abs_token == "a-token"
    assert cfg.abs_library_id == "lib-7"
    assert cfg.voice == "bm_george"
    assert cfg.embed_model == "some/other-model"
    assert cfg.agent_model == "claude-sonnet-5"


def test_the_sdks_own_key_variable_is_honoured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """So the key can be set the way every other Anthropic tool expects."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert load_config().anthropic_api_key == "sk-test"


@pytest.mark.parametrize("level", ["low", "medium", "high", "xhigh", "max"])
def test_every_effort_level_the_api_accepts_is_accepted_here(
    monkeypatch: pytest.MonkeyPatch, level: str
) -> None:
    """The list is the API's, and a level missing from it would be a 400 at 2am."""
    monkeypatch.setenv("SOMNIA_AGENT_EFFORT", level)
    assert load_config().agent_effort == level


def test_an_empty_variable_is_not_an_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`FOO=` in a unit file is a variable somebody meant to unset.

    The loader reads with `:=`, so an empty string falls through to the default
    rather than blanking the setting — which for the voice would be a render
    with no narrator named at all.
    """
    monkeypatch.setenv("SOMNIA_VOICE", "")
    monkeypatch.setenv("SOMNIA_ABS_URL", "")
    cfg = load_config()
    assert cfg.voice == Config().voice
    assert cfg.abs_url == Config().abs_url
