# somnia chart

Deploys somnia as two things beside each other: the page (`somnia serve`) and
the renderer (`somnia worker`), sharing one volume.

```bash
helm install somnia oci://ghcr.io/gilesknap/charts/somnia \
  --namespace somnia --create-namespace \
  --set node=node03 \
  --set persistence.storageClassName=local-nvme
```

## The one thing you cannot change

**Both pods must run on the same node, and it must be the node the volume is
on.** That is what `node` does, and it is not a placement preference.

somnia keeps everything in one sqlite file — the catalog, the index, the saved
position and the ingest queue — and opens it in WAL mode. WAL coordinates its
writers through a shared-memory file that every connection maps, which works
between processes on one machine and does not work between two, on any
filesystem. The audio is the same story: the renderer writes chapters into the
library directory and the page serves them straight off it.

So the renderer cannot be moved to a different node from the page. Doing it
does not produce an error message; it produces a database that two machines
disagree about.

Splitting them, or running renders on several machines at once, needs the
coordination to stop being a shared file — see the deployment guide in the main
docs for what that would take.

## Values worth knowing

| Value | Default | Notes |
| --- | --- | --- |
| `node` | `""` | Hostname both pods pin to. Set it. |
| `persistence.storageClassName` | `""` | Cluster default. Name your local class here. |
| `persistence.size` | `100Gi` | ~30MB per hour of book, doubled for anything listened to, plus ~1GB of models. |
| `persistence.existingClaim` | `""` | Use a claim you already have instead of making one. |
| `secret.name` | `""` | Existing Secret holding `ANTHROPIC_API_KEY`. Without it everything works except asking questions. |
| `ingress.enabled` | `false` | See below. |
| `worker.resources.limits.cpu` | `6` | The renderer's leash, so it cannot take the cores the page needs. |

`config.voice`, `config.embedModel`, `config.agentModel` and
`config.agentEffort` map to the `SOMNIA_*` environment variables of the same
name. Leaving one empty leaves the default in `somnia/config.py` alone.

## Getting to the page

somnia has **no login**. On a box it binds `127.0.0.1` and only
`tailscale serve` can reach it — reachability *is* the authentication. In a pod
it has to bind `0.0.0.0`, so whatever you put in front of it is the whole of
the security.

The intended answer is the [Tailscale Kubernetes
operator](https://tailscale.com/kb/1236/kubernetes-operator), which puts the
service on your tailnet with a real certificate and keeps the model the box
has:

```yaml
ingress:
  enabled: true
  className: tailscale
  host: somnia          # becomes somnia.<your-tailnet>.ts.net
  tls:
    enabled: true       # the operator issues the certificate
```

The certificate is not a nicety. The page registers a service worker, and
browsers only allow that in a secure context — over plain HTTP somnia stops
being an installable PWA and you lose the lock-screen controls, which is most
of the point of it at 2am.

An nginx ingress works too, but put authentication in front of it via
`ingress.annotations`.

## Adding a book

```bash
kubectl -n somnia exec deploy/somnia-worker -- somnia catalog-update
kubectl -n somnia exec deploy/somnia-worker -- somnia search "treasure island"
kubectl -n somnia exec deploy/somnia-worker -- somnia queue add 120
kubectl -n somnia exec deploy/somnia-worker -- somnia queue
```

The worker notices within ten seconds. A book takes hours; the page can play
what has been rendered while the rest arrives.
