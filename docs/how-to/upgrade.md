# Upgrade to a new version

```bash
somnia --version
```

Released versions are on the [releases
page](https://github.com/gilesknap/somnia/releases) and on PyPI as
[somnia-reader](https://pypi.org/project/somnia-reader/) — `somnia` there is an
unrelated project and always was. Upgrading means either taking the newer
release or pointing pip at a different git ref; the second is how you get a fix
that has landed on `main` but has not been tagged yet.

## With the installer

```bash
bash somnia-install.sh --ref 0.6     # a git tag, branch or commit
bash somnia-install.sh --pypi        # the last release from PyPI
```

It reuses the environment it finds, replaces somnia inside it, and leaves your
settings file alone. Add `--serve-only` if that is what the box is, and the same
`--venv` you installed with if it was not the default.

## By hand

```bash
source ~/somnia-venv/bin/activate
python3 -m pip uninstall -y somnia-reader
python3 -m pip install "somnia-reader[ml] @ git+https://github.com/gilesknap/somnia.git@0.6"
```

Uninstall by the *distribution* name, `somnia-reader` — `pip uninstall somnia`
finds nothing to remove and exits happily, which looks exactly like success.

The uninstall itself is not superstition either. pip treats a direct URL
requirement as satisfied when the name and version already match, so re-running
the install command with a new `--ref` clones the repository, decides there is
nothing to do, and leaves you on the old version — with no error to notice. (The
installer gets around this by force-reinstalling somnia and nothing else, which
is why it does not disturb your two gigabytes of torch.)

Upgrading to a *release* needs no uninstall, because a plain
`pip install --upgrade "somnia-reader[ml]"` compares versions rather than
shrugging at a URL.

## What survives it

**The database migrates itself.** Columns added since your version are added by
the next command that opens it. Nothing is dropped and nothing is rewritten, so
positions, high-water marks and the index come through unchanged.

**The audio is untouched**, and so is `~/somnia.env`. Nothing in an upgrade
re-renders a book or asks you to.

## Afterwards

```bash
systemctl --user restart somnia-serve
bash somnia-doctor.sh
```

The doctor is the check worth running, because it looks at the install and the
data together. `curl -s localhost:8721/api/health` answers `{"ok": true}` once
the service is back.

On the phone, the page updates itself: the new service worker takes over as
soon as it is fetched, and drops the caches belonging to older versions. Closing
the app and opening it again is enough to be sure — and worth doing before a
night rather than during one.

## Going back

There is no downgrade path, and no test that says an older somnia is happy with
a newer database. Migrations only ever add columns, so in practice older code
ignores what it does not know about, but if the upgrade is one you might want to
reverse, take a copy of `somnia.db` first — see
[Back it up, and move it](back-up-and-move.md).

## In a container

```bash
docker pull ghcr.io/gilesknap/somnia:0.6
```

Same story for the data: the database and the library live outside the image,
and the new container migrates the database it is given.
