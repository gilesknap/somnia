# Run in a container

Pre-built containers with somnia and its dependencies already
installed are available on [Github Container Registry](https://ghcr.io/gilesknap/somnia).

The image carries somnia and its Python dependencies only — no torch, no
Kokoro, no ffmpeg, no espeak-ng. It can answer `--version` and the light
subcommands; rendering or serving a book from it is not a supported path today.

## Starting the container

To pull the container from github container registry and run:

```
$ docker run ghcr.io/gilesknap/somnia:latest --version
```

To get a released version, use a numbered release instead of `latest`.
