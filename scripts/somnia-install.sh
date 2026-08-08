#!/usr/bin/env bash
#
# Install somnia into a virtual environment of its own.
#
# somnia has two halves with different appetites. The machine that *renders*
# books needs Kokoro, torch, ffmpeg and espeak-ng; the machine that only
# *serves* them needs none of that. Pass --serve-only for the second kind.
# Most of the time they are the same VPS, and the default is that machine.
#
# Usage: somnia-install.sh [options]
#
#   --venv DIR       build the environment here (default ~/somnia-venv)
#   --env-file FILE  seed this settings file if it is absent (default ~/somnia.env)
#   --ref REF        install this branch, tag or commit (default main)
#   --source SPEC    install from a checkout instead of GitHub
#   --serve-only     no Kokoro and no torch: this machine only plays books
#   --cuda           take the CUDA torch wheel; the default is CPU-only
#   --no-catalog     skip the Gutenberg catalog download
#   -h, --help       print this and stop
#
# It is safe to run twice: an existing environment is reused, and a settings
# file that already exists is never touched.

set -euo pipefail

# somnia is not on PyPI. The name is taken there by an unrelated project, so
# installing it by name gets you somebody else's package — always the git URL.
REPO_URL=${SOMNIA_REPO_URL:-https://github.com/gilesknap/somnia.git}
CPU_TORCH_INDEX=https://download.pytorch.org/whl/cpu

venv=$HOME/somnia-venv
env_file=$HOME/somnia.env
ref=main
source_spec=""
render=yes
cpu_torch=yes
catalog=yes

if [ -t 1 ]; then
    bold=$(printf '\033[1m')
    reset=$(printf '\033[0m')
else
    bold=""
    reset=""
fi

say() { printf '%s==>%s %s\n' "$bold" "$reset" "$*"; }
warn() { printf '  !  %s\n' "$*" >&2; }
die() {
    printf 'xx %s\n' "$*" >&2
    exit 1
}
usage() { sed -n '3,25p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case $1 in
    --venv)
        venv=${2:?--venv needs a directory}
        shift 2
        ;;
    --env-file)
        env_file=${2:?--env-file needs a path}
        shift 2
        ;;
    --ref)
        ref=${2:?--ref needs a branch, tag or commit}
        shift 2
        ;;
    --source)
        source_spec=${2:?--source needs a path}
        shift 2
        ;;
    --serve-only)
        render=no
        shift
        ;;
    --cuda)
        cpu_torch=no
        shift
        ;;
    --no-catalog)
        catalog=no
        shift
        ;;
    -h | --help)
        usage
        exit 0
        ;;
    *) die "unknown option: $1 (try --help)" ;;
    esac
done

# --- an interpreter somnia can run on ---------------------------------------
#
# 3.14 is held back by pysbd, the sentence splitter: its non-raw-string escape
# sequences are a hard SyntaxError there. Prefer the newest version we can use
# rather than whatever `python3` happens to be.

# An interpreter has to be able to *build* a virtual environment, not merely to
# run — on Debian and Ubuntu `python3-venv` is a separate package, and without
# it `python3 -m venv` gets all the way to writing the directory before failing
# with a message about ensurepip that names no part of somnia. Checking here
# costs one subprocess and turns that into a sentence saying what to install.
# `venv_package_hint` carries the name of the one that was so nearly right, so
# the error can name a package rather than a category.
venv_package_hint=""

usable_python() {
    "$1" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info < (3, 14)))' 2>/dev/null || return 1
    if ! "$1" -c 'import ensurepip' 2>/dev/null; then
        venv_package_hint="python$("$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)-venv"
        return 1
    fi
    return 0
}

# The answer comes back in `found_python` rather than on stdout, because the
# caller would have to write `$(find_python)` to read stdout and that runs the
# whole search in a subshell — where `venv_package_hint` is set, and where it
# dies along with the subshell. The diagnosis has to outlive the search.
found_python=""

find_python() {
    local candidate
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1 && usable_python "$candidate"; then
            found_python=$(command -v "$candidate")
            return 0
        fi
    done
    # A box whose only python3 is 3.14 is now the common case rather than an
    # odd one. uv keeps interpreters of its own, off PATH, and any of those
    # will do. --system so that running this from inside a checkout finds a
    # real interpreter rather than that checkout's own virtual environment.
    # These always carry ensurepip, so they skip the check above — and must,
    # since no apt package would fix one of them anyway.
    if command -v uv >/dev/null 2>&1; then
        found_python=$(uv python find --system '>=3.11,<3.14' 2>/dev/null) &&
            [ -n "$found_python" ] && return 0
    fi
    found_python=""
    return 1
}

if find_python; then
    python=$found_python
else
    if [ -n "$venv_package_hint" ]; then
        die "somnia found a Python it can use but it cannot build a virtual" \
            "environment — run: sudo apt install $venv_package_hint"
    fi
    hint="install one with your package manager"
    command -v uv >/dev/null 2>&1 && hint="run: uv python install 3.13"
    die "somnia needs Python 3.11, 3.12 or 3.13, and none of those was found — $hint"
fi
say "python: $python ($("$python" -c 'import platform; print(platform.python_version())'))"

# --- system packages ---------------------------------------------------------
#
# Only the render host needs these, and neither can be installed from pip, so a
# missing one is a warning with the command to fix it rather than a stop: the
# environment is still worth building.

if [ "$render" = yes ]; then
    missing=""
    command -v ffmpeg >/dev/null 2>&1 || missing="$missing ffmpeg"
    command -v espeak-ng >/dev/null 2>&1 || missing="$missing espeak-ng"

    if [ -n "$missing" ]; then
        if command -v apt-get >/dev/null 2>&1; then
            fix="sudo apt install$missing"
        elif command -v dnf >/dev/null 2>&1; then
            fix="sudo dnf install$missing"
        elif command -v pacman >/dev/null 2>&1; then
            fix="sudo pacman -S$missing"
        elif command -v brew >/dev/null 2>&1; then
            fix="brew install$missing"
        else
            fix="install these with your package manager:$missing"
        fi
        warn "missing:$missing — rendering will fail until you run: $fix"
    else
        say "ffmpeg and espeak-ng: found"
    fi
fi

# --- the environment ---------------------------------------------------------

if [ -d "$venv" ]; then
    say "reusing the environment at $venv"
else
    say "building an environment at $venv"
    "$python" -m venv "$venv"
fi

vpy="$venv/bin/python"
[ -x "$vpy" ] || die "$venv exists but has no bin/python in it"

say "updating pip"
"$vpy" -m pip install --quiet --upgrade pip

# --- torch, before anything that wants it ------------------------------------
#
# --extra-index-url is not enough to get the CPU wheel. pip resolves across
# both indexes and takes the highest version it finds, so the moment PyPI
# carries a newer torch than the CPU index does, you get two gigabytes of CUDA
# runtime to render a book with. Installing torch first, from the CPU index
# alone, is the only form that cannot pick the wrong wheel — after which
# somnia[ml] finds its torch requirement already satisfied.

if [ "$render" = yes ] && [ "$cpu_torch" = yes ]; then
    say "installing CPU torch from $CPU_TORCH_INDEX"
    "$vpy" -m pip install --quiet torch --index-url "$CPU_TORCH_INDEX"
fi

# --- somnia ------------------------------------------------------------------

extras=""
[ "$render" = yes ] && extras="[ml]"

if [ -n "$source_spec" ]; then
    [ -f "$source_spec/pyproject.toml" ] || die "no pyproject.toml under $source_spec"
    spec="$source_spec$extras"
else
    spec="somnia$extras @ git+$REPO_URL@$ref"
fi

# Two passes, because pip will not reinstall a package whose name and version
# it already has: a plain install of a new --ref into an existing environment
# clones the repo, decides it is satisfied and changes nothing, which would
# make this script useless for upgrading. The first pass replaces somnia and
# only somnia; the second brings in any dependency the new version added,
# without disturbing the ones — torch, above all — that are already right.
say "installing $spec"
"$vpy" -m pip install --quiet --force-reinstall --no-deps "$spec"
"$vpy" -m pip install --quiet "$spec"

# --- settings ----------------------------------------------------------------
#
# systemd's EnvironmentFile= does no variable expansion, so the paths written
# here are expanded now rather than left as $HOME.

if [ -e "$env_file" ]; then
    say "leaving $env_file alone (it already exists)"
else
    say "writing a starter $env_file"
    cat >"$env_file" <<EOF
# somnia settings. Read by your shell (source this file) and by the systemd
# units in the how-to guides (EnvironmentFile=). No variable expansion happens
# in here: write paths out in full.

# The only setting with no working default. Required by 'somnia ask' and
# 'somnia serve'; rendering and searching do not need it.
ANTHROPIC_API_KEY=

# Where somnia.db lives.
#SOMNIA_DATA_DIR=$HOME/.local/share/somnia

# Where rendered chapters are written, and served from. This is the one that
# fails quietly: get it wrong and the server starts happily and 404s every
# chapter. Set it explicitly if it is not the default.
#SOMNIA_LIBRARY_DIR=$HOME/library/audiobooks

# The Kokoro voice. Never change this for a book already rendered.
#SOMNIA_VOICE=af_heart

# The model behind the conversation.
#SOMNIA_AGENT_MODEL=claude-sonnet-5

# Must be 384-dimensional.
#SOMNIA_EMBED_MODEL=intfloat/e5-small-v2

# Audiobookshelf, if you run one. Leave the token unset and no ABS client is
# built at all. The library id comes from 'somnia libraries'.
#SOMNIA_ABS_URL=http://127.0.0.1:13378
#SOMNIA_ABS_TOKEN=
#SOMNIA_ABS_LIBRARY_ID=
EOF
    chmod 600 "$env_file"
fi

# --- did it work -------------------------------------------------------------

say "somnia $("$venv/bin/somnia" --version)"

if [ "$render" = yes ]; then
    cuda=$("$vpy" -c 'import torch; print(torch.version.cuda)')
    if [ "$cuda" = None ]; then
        say "torch $("$vpy" -c 'import torch; print(torch.__version__)') (CPU)"
    else
        warn "torch was built for CUDA $cuda — that is 2GB of GPU runtime this box may not have"
    fi
fi

if [ "$catalog" = yes ]; then
    say "pulling the Gutenberg catalog (~20MB, once)"
    "$venv/bin/somnia" catalog-update
fi

cat <<EOF

${bold}Installed.${reset} Next:

  1. Put your Anthropic key in $env_file
  2. source $env_file
  3. export PATH="$venv/bin:\$PATH"    # or call $venv/bin/somnia in full
  4. somnia search "black beauty"      # then: somnia add 271

Run somnia-doctor.sh at any point to check the whole install over.
EOF
