# Deploy to a Kubernetes cluster

somnia ships a Helm chart. It runs the page and the renderer as two deployments
on one node, sharing one volume — the same shape as the two systemd units in
[Keep a long render running](keep-renders-running.md), moved onto a cluster.

```bash
helm install somnia oci://ghcr.io/gilesknap/charts/somnia \
  --namespace somnia --create-namespace \
  --set node=node03 \
  --set persistence.storageClassName=local-nvme \
  --set secret.name=somnia-env
```

The chart's own [README](https://github.com/gilesknap/somnia/tree/main/Charts/somnia)
is the reference for every value. This page is about the two decisions that are
not obvious.

## Why both halves land on one node

The obvious thing to want from a cluster is the page on one machine and the
renderer on another — the page is latency-sensitive and the renderer eats
cores, and separating them looks like exactly what a scheduler is for.

It cannot be done, and the reason is not the scheduler.

Everything somnia knows is in one sqlite file: the catalog, the chunk index and
its vectors, where the listener has got to, and the ingest queue. That is a
deliberate choice — it is why a render's progress can be read by a process that
is not doing the rendering, with no lock file and no socket. The file is opened
in WAL mode, and WAL coordinates writers through a shared-memory file that
every connection maps into its own address space. Two processes on one machine
share it. Two machines cannot, on any filesystem: not NFS, not anything. The
audio is the same story from the other end — the renderer writes chapters into
the library directory and the page serves them straight off the disk beside it.

Put the two on different nodes and nothing raises an error. You get two
machines with different ideas about what is in the library and where the
listener is.

So `node` in the chart pins both deployments to one hostname, and that hostname
has to be where the volume is. On a cluster whose storage is node-pinned local
volumes, all three facts have to agree.

The claim is `ReadWriteOnce`, which is not the restriction it looks like: RWO
is once per *node*, not once per pod, so both pods mount it read-write.

### What separating them would take

Cross-node placement, and rendering several books at once on several machines,
are the same problem: the coordination has to stop being a shared file. Roughly,
either

- move the queue and the index into a real database — Postgres with pgvector
  is a close match for what `somnia.db` already does, and is a thing clusters
  tend to have — and put the audio on shared storage; or
- stop sharing at all: give the renderer an HTTP client and let the server be
  the only thing that touches the database.

Both are real work and neither is a chart change. Note that the ARM NPU
question is downstream of this one — accelerating a render is worth little if
only one machine can run a render at a time.

## Getting to the page

somnia has no login. The security model is that only your tailnet can reach it
([the architecture](../explanations/architecture.md) has the whole argument),
and in a pod that model is gone the moment the server binds `0.0.0.0` — which
it must, because nothing can reach a pod's localhost.

So `ingress.enabled` defaults to `false`, and the intended way to turn it on is
the [Tailscale Kubernetes
operator](https://tailscale.com/kb/1236/kubernetes-operator):

```yaml
ingress:
  enabled: true
  className: tailscale
  host: somnia
  tls:
    enabled: true
```

That gives you `somnia.<tailnet>.ts.net` with a real certificate, reachable by
your devices and nothing else — the cluster equivalent of `tailscale serve`.

Use a real certificate whichever route you take. The page registers a service
worker, browsers only allow that over HTTPS, and without it somnia is a web
page rather than an installed app: no lock screen, no Bluetooth buttons, no
sleep timer surviving the screen going off.

If you front it with nginx instead, put something in `ingress.annotations` that
authenticates. Be aware that an OAuth redirect is a poor fit here — the thing
being protected is used half asleep in the dark, and the audio element and the
page's own fetches all have to pass it too.

## The image

The published image is multi-architecture — `linux/amd64` and `linux/arm64` —
so it runs on an ARM node without anything special. It carries torch, Kokoro,
ffmpeg and espeak-ng, which is what makes it able to render and serve rather
than only answer `--version`.

torch in it is the CPU build, pinned in `pyproject.toml`. Left to itself, torch
on Linux pulls the whole CUDA stack, including on arm64 where those libraries
are for Grace and Jetson and are useless on anything else — several gigabytes
of an image that cannot load them. somnia has never wanted a GPU: the renderer
is Kokoro on cores and the embedder is small enough that moving it to a card
would cost more than it saved.

## First run

The models — the embedder and Kokoro — are fetched from Hugging Face the first
time they are used, into `HF_HOME` on the data volume. That is a few hundred
megabytes and it happens once; after that a restart is cold only in the sense
that it reads them off disk. Until it finishes, the first question of the night
waits.

Then add a book:

```bash
kubectl -n somnia exec deploy/somnia-worker -- somnia catalog-update
kubectl -n somnia exec deploy/somnia-worker -- somnia queue add 271
kubectl -n somnia exec deploy/somnia-worker -- somnia queue
```

## The API key

Only the agent lane needs `ANTHROPIC_API_KEY`. The chart does not create a
Secret — point `secret.name` at one you made, or at a SealedSecret if the
cluster is GitOps-managed:

```bash
kubectl -n somnia create secret generic somnia-env \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-...
```

Without it, books still render and the page still plays them. Asking a question
is what stops working.

## Backing it up

Everything that matters is on the one volume, and none of it is cheap to make
again — a book is hours of rendering. The claim carries
`helm.sh/resource-policy: keep`, so deleting the release leaves it alone, but
that is not a backup. [Back up and move](back-up-and-move.md) applies unchanged;
run it against the volume.
