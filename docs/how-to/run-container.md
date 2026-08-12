# Run in a container

Pre-built containers with somnia and its dependencies already
installed are available on [Github Container Registry](https://ghcr.io/gilesknap/somnia).

The image carries everything a render and a night need: torch, Kokoro,
sentence-transformers, ffmpeg and espeak-ng. It is published for both
`linux/amd64` and `linux/arm64`, so the same tag runs on a workstation and on
an ARM single-board machine.

torch in it is the CPU build. somnia does not want a GPU — the renderer is
Kokoro on cores and the embedder is small — and pinning it keeps the image
around a gigabyte instead of the eight the CUDA stack would add.

## Starting the container

To pull the container from github container registry and run:

```
$ docker run ghcr.io/gilesknap/somnia:latest --version
```

To get a released version, use a numbered release instead of `latest`.

## Keeping what it makes

The image points `SOMNIA_DATA_DIR`, `SOMNIA_LIBRARY_DIR` and `HF_HOME` at
`/data`. Mount something there or every book, and both downloaded models, die
with the container:

```bash
docker run -v somnia-data:/data ghcr.io/gilesknap/somnia:latest queue add 271
docker run -v somnia-data:/data ghcr.io/gilesknap/somnia:latest worker --once
```

## Serving the page

`serve` binds `127.0.0.1` by default, which inside a container means nothing
outside it can connect. Bind `0.0.0.0` and publish the port:

```bash
docker run -v somnia-data:/data -p 8721:8721 \
  -e ANTHROPIC_API_KEY \
  ghcr.io/gilesknap/somnia:latest serve --host 0.0.0.0 --port 8721
```

That undoes somnia's only defence — it has no login, and on a box the fact that
only `tailscale serve` can reach the port *is* the authentication. Publish it
to a network you trust, and put TLS in front of it: the page registers a
service worker, and browsers only allow that in a secure context, so over plain
HTTP it will play a book but will not install as an app or drive the lock
screen.

## Running the two halves

The renderer and the page are separate processes on purpose — restarting the
page must not kill a six-hour render. Two containers, one volume, both on the
same machine:

```bash
docker run -d -v somnia-data:/data --name somnia-worker \
  ghcr.io/gilesknap/somnia:latest worker
docker run -d -v somnia-data:/data -p 8721:8721 --name somnia-serve \
  -e ANTHROPIC_API_KEY \
  ghcr.io/gilesknap/somnia:latest serve --host 0.0.0.0
```

Same machine is not a suggestion. The two coordinate through one sqlite file in
WAL mode, which processes on one host share and two hosts cannot.

On a cluster, the chart does all of this for you — see
[Deploy to a Kubernetes cluster](deploy-to-kubernetes.md).
