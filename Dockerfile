# The devcontainer should use the developer target and run as root with podman
# or docker with user namespaces.
FROM ghcr.io/diamondlightsource/ubuntu-devcontainer:noble AS developer

# Add any system dependencies for the developer/build environment here
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    graphviz \
    && apt-get dist-clean

# The build stage installs the context into the venv
FROM developer AS build

# Change the working directory to the `app` directory
# and copy in the project
WORKDIR /app
COPY . /app
RUN chmod o+wrX .

# Tell uv sync to install python in a known location so we can copy it out later
ENV UV_PYTHON_INSTALL_DIR=/python

# Sync the project with the ml extra, and without its dev dependencies.
#
# `--extra ml` is what makes this image able to do anything. Without it the
# image carried no torch, no Kokoro and no sentence-transformers, and could
# answer `--version` and little else. Note that it is not only the renderer
# that wants it: `somnia serve` warms the embedder on the way up and every
# semantic seek goes through it, so the page needs torch just as much as the
# worker does. Kokoro is the only half that is genuinely renderer-only, and
# splitting the image over one dependency is not worth two images to keep in
# step.
#
# torch here is the CPU build, pinned in pyproject's [tool.uv.sources]. That
# pin is the reason this image is about a gigabyte instead of about eight, and
# the reason there is an arm64 image at all.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --no-dev --extra ml --managed-python


# The runtime stage copies the built venv into a runtime container
FROM ubuntu:noble AS runtime

# ffmpeg joins the chapters the page plays and encodes what Kokoro produces;
# espeak-ng is the phonemiser Kokoro falls back to for anything its own
# dictionary does not cover; libgomp1 is OpenMP, which the torch CPU wheel
# links against and ubuntu:noble does not ship. `somnia-doctor.sh` checks for
# the first two by name — a render fails without them, and it fails hours in.
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    ffmpeg \
    espeak-ng \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy the python installation from the build stage
COPY --from=build /python /python

# Copy the environment, but not the source code
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH

# Both models somnia loads — the embedder and Kokoro — are fetched from
# Hugging Face on first use. Left at the default they would land in root's home
# and be downloaded again after every pod restart, which on a 2am appliance
# means the first question of the night waits on a download. Pointed at the
# data directory, they are fetched once and live on the same volume as the
# database. The chart mounts a PVC there; `docker run` without one gets the
# old behaviour and pays the download each time.
ENV HF_HOME=/data/huggingface
ENV SOMNIA_DATA_DIR=/data
ENV SOMNIA_LIBRARY_DIR=/data/library

# change this entrypoint if it is not the same as the repo
ENTRYPOINT ["somnia"]
CMD ["--version"]
