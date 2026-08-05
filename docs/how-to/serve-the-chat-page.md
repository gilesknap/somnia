# Serve the chat page

`somnia serve` runs the 2am surface: a small chat page that talks to the agent,
with the Anthropic key held server-side. Voice input uses the browser's Web
Speech API, so the page must be reached over HTTPS (or localhost) — `tailscale
serve` provides both the certificate and the only network path to it.

## Run it

```
$ somnia serve                       # 127.0.0.1:8721 by default
$ somnia serve --host 0.0.0.0 --port 9000
```

It needs the same environment as the rest of somnia, plus a key for the model:

| Variable | Why |
|---|---|
| `ANTHROPIC_API_KEY` | the agent's model calls, paid by you not the phone |
| `SOMNIA_ABS_URL`, `SOMNIA_ABS_TOKEN` | reading listening position, planting bookmarks |
| `SOMNIA_DATA_DIR` | where `somnia.db` lives, if not the default |
| `SOMNIA_AGENT_MODEL` | override Haiku for harder disambiguation |

**Keep `--host` as localhost.** The page has no login of any kind: anyone who
can reach it can drive the agent and spend your API credit. Its only protection
is that nothing but `tailscale serve` can reach the port.

## Publish it on the tailnet

Audiobookshelf usually already holds port 443, so give the chat page its own:

```
$ tailscale serve --bg --https 8443 http://127.0.0.1:8721
$ tailscale serve status
```

The page is then at `https://<node>.<tailnet>.ts.net:8443/`, reachable from
your own devices and from nowhere else. Open it on the phone and use the
browser's *Add to home screen* — it installs as a standalone app with its own
icon, which is one tap in the dark instead of a browser and a URL.

## Keep it running

As a systemd **user** service, alongside the rest of somnia:

```ini
# ~/.config/systemd/user/somnia-serve.service
[Unit]
Description=somnia chat page
After=network-online.target

[Service]
EnvironmentFile=%h/somnia.env
ExecStart=%h/.local/bin/somnia serve
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

```
$ loginctl enable-linger $USER          # survive logout
$ systemctl --user daemon-reload
$ systemctl --user enable --now somnia-serve
$ curl -s localhost:8721/api/health     # {"ok": true}
```

## Using it

Type, or hold the button and speak — it listens only while held, because a
bedroom is full of speech that was not meant for somnia. Spoken questions are
answered out loud; typed ones are not.

Conversations are held in memory, keyed by a token the page mints when it
starts, and nothing is written to disk. *Start over* drops the history when the
agent has got the wrong end of a mumbled question; restarting the service drops
all of them.
