#!/usr/bin/env bash
#
# Check a somnia install over and say what is wrong with it.
#
# Most of what goes wrong with somnia goes wrong quietly: a library directory
# pointing at nothing serves a page that answers questions happily and 404s
# every chapter, and a chapter row pointing outside that directory is refused
# even though the file is there. This looks for those.
#
# Usage: somnia-doctor.sh [options]
#
#   --venv DIR       the environment to check (default ~/somnia-venv)
#   --env-file FILE  settings to load first (default ~/somnia.env)
#   --url URL        a running server to ask for health (default http://127.0.0.1:8721)
#   -h, --help       print this and stop
#
# Exit status is 0 if nothing failed, 1 if anything did. Warnings do not fail:
# a serving-only box is meant to have no torch.

set -euo pipefail

venv=$HOME/somnia-venv
env_file=$HOME/somnia.env
url=http://127.0.0.1:8721

if [ -t 1 ]; then
    bold=$(printf '\033[1m')
    reset=$(printf '\033[0m')
else
    bold=""
    reset=""
fi

usage() { sed -n '3,19p' "$0" | sed 's/^# \{0,1\}//'; }

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
    --url)
        url=${2:?--url needs a URL}
        shift 2
        ;;
    -h | --help)
        usage
        exit 0
        ;;
    *)
        printf 'xx unknown option: %s (try --help)\n' "$1" >&2
        exit 1
        ;;
    esac
done

fails=0
warns=0

report() {
    case $1 in
    ok) printf '  ok    %s\n' "$2" ;;
    warn)
        printf '  warn  %s\n' "$2"
        warns=$((warns + 1))
        ;;
    fail)
        printf '  FAIL  %s\n' "$2"
        fails=$((fails + 1))
        ;;
    esac
}

printf '%ssomnia doctor%s\n\n' "$bold" "$reset"

# --- the environment ---------------------------------------------------------

if [ -x "$venv/bin/somnia" ]; then
    report ok "somnia $("$venv/bin/somnia" --version) in $venv"
else
    report fail "no somnia in $venv — run somnia-install.sh, or pass --venv"
    printf '\n%d failed, %d warned\n' "$fails" "$warns"
    exit 1
fi

vpy="$venv/bin/python"
pyversion=$("$vpy" -c 'import platform; print(platform.python_version())')
if "$vpy" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info < (3, 14)))'; then
    report ok "python $pyversion"
else
    report fail "python $pyversion — somnia needs 3.11, 3.12 or 3.13"
fi

# --- settings ----------------------------------------------------------------
#
# Load the settings file the same way a systemd unit would, so this checks what
# the service will actually see rather than what this shell happens to hold.

if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090  # the path is an option, not a fixed file
    . "$env_file"
    set +a
    report ok "settings from $env_file"
else
    report warn "no $env_file — checking the environment this shell already has"
fi

# --- rendering -----------------------------------------------------------------

for tool in ffmpeg espeak-ng; do
    if command -v "$tool" >/dev/null 2>&1; then
        report ok "$tool"
    else
        report warn "no $tool — this box cannot render books (fine if it only serves)"
    fi
done

if cuda=$("$vpy" -c 'import torch; print(torch.version.cuda)' 2>/dev/null); then
    version=$("$vpy" -c 'import torch; print(torch.__version__)')
    if [ "$cuda" = None ]; then
        report ok "torch $version (CPU)"
    else
        report warn "torch $version is a CUDA build — 2GB of GPU runtime, on a box that may have no GPU"
    fi
else
    report warn "no torch — this box cannot render books (fine if it only serves)"
fi

# --- everything somnia itself can see ------------------------------------------
#
# Asked through somnia's own config loader, so this cannot drift from what the
# server reads. Each line comes back as a level and a message.

while IFS=$'\t' read -r level message; do
    [ -n "$level" ] && report "$level" "$message"
done < <(
    "$vpy" - <<'PY'
import sqlite3
from pathlib import Path

from somnia.config import load_config


def say(level, message):
    print(f"{level}\t{message}")


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


cfg = load_config()

if cfg.anthropic_api_key:
    say("ok", "ANTHROPIC_API_KEY is set")
else:
    say("fail", "ANTHROPIC_API_KEY is unset — 'somnia ask' and 'somnia serve' cannot run")

if not cfg.data_dir.is_dir():
    say("warn", f"no data directory at {cfg.data_dir} — nothing has been run yet")
elif not cfg.db_path.exists():
    say("warn", f"no database at {cfg.db_path} — run 'somnia catalog-update'")
else:
    # Read-only, and by URI so a typo in SOMNIA_DATA_DIR cannot quietly create
    # an empty database here.
    db = sqlite3.connect(f"file:{cfg.db_path}?mode=ro", uri=True)
    count = lambda sql: db.execute(sql).fetchone()[0]  # noqa: E731

    catalogued = count("SELECT count(*) FROM catalog")
    if catalogued:
        say("ok", f"catalog: {plural(catalogued, 'book', 'books')} to search")
    else:
        say("fail", "the catalog is empty — run 'somnia catalog-update'")

    books = count("SELECT count(*) FROM books")
    done = count("SELECT count(*) FROM books WHERE status = 'done'")
    if books:
        say("ok", f"library: {plural(books, 'book', 'books')}, {done} fully rendered")
    else:
        say("warn", "no books added yet — try 'somnia add 271'")

    # The quiet failure. Chapters are looked up in the database and never by
    # path, so a library directory that has moved shows up on the phone as one
    # chapter that didn't arrive, and nowhere else.
    library = cfg.library_dir.resolve()
    rows = db.execute("SELECT book_gid, idx, audio_file FROM chapters").fetchall()
    absent = [r for r in rows if not Path(r[2]).exists()]
    outside = [r for r in rows if library not in Path(r[2]).resolve().parents]

    if rows and not absent and not outside:
        say("ok", f"all {len(rows)} rendered chapters are present under {library}")
    if absent:
        say("fail", f"{len(absent)} of {len(rows)} chapters are missing from disk "
                    f"— first: {absent[0][2]}")
    if outside:
        say("fail", f"{plural(len(outside), 'chapter sits', 'chapters sit')} outside "
                    f"SOMNIA_LIBRARY_DIR ({library}), and the server refuses those "
                    f"— first: {outside[0][2]}")

    db.close()

if not cfg.library_dir.is_dir():
    say("warn", f"no library directory at {cfg.library_dir} — 'somnia add' will create it")
PY
)

# --- a running server ----------------------------------------------------------

if command -v curl >/dev/null 2>&1; then
    if health=$(curl -fsS --max-time 3 "$url/api/health" 2>/dev/null); then
        report ok "server at $url says $health"
    else
        report warn "nothing answering at $url (only a problem if it should be running)"
    fi
fi

printf '\n%d failed, %d warned\n' "$fails" "$warns"
[ "$fails" -eq 0 ]
