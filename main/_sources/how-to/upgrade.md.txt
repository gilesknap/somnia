# Upgrade to a new version

```bash
somnia --version
```

Released versions are on the [releases
page](https://github.com/gilesknap/somnia/releases). There is no PyPI package —
that name belongs to another project
([#9](https://github.com/gilesknap/somnia/issues/9)) — so upgrading means
pointing pip at a different git ref.

## With the installer

```bash
bash somnia-install.sh --ref 0.6
```

It reuses the environment it finds, replaces somnia inside it, and leaves your
settings file alone. Add `--serve-only` if that is what the box is, and the same
`--venv` you installed with if it was not the default.

## By hand

```bash
source ~/somnia-venv/bin/activate
python3 -m pip uninstall -y somnia
python3 -m pip install "somnia[ml] @ git+https://github.com/gilesknap/somnia.git@0.6"
```

The uninstall is not superstition. pip treats a direct URL requirement as
satisfied when the name and version already match, so re-running the install
command with a new `--ref` clones the repository, decides there is nothing to
do, and leaves you on the old version — with no error to notice. (The installer
gets around this by force-reinstalling somnia and nothing else, which is why it
does not disturb your two gigabytes of torch.)

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
