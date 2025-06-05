# syntax=docker/dockerfile:1
ARG PY_VER=3.12-slim
ARG PLAYWRIGHT_VERSION=1.52.0
ARG EXTRA_APT=""            # <-- packages injected from prefs

FROM python:${PY_VER}
# make build-args available in this stage ↓
ARG EXTRA_APT
ARG PLAYWRIGHT_VERSION


# --- switch all Debian mirrors to HTTPS (bookworm uses *.sources) ----
RUN set -e ; \
    if [ -f /etc/apt/sources.list ]; then \
        sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list ; \
    fi ; \
    find /etc/apt/sources.list.d -name '*.sources' -print0 \
         | xargs -0 sed -i 's|http://deb.debian.org|https://deb.debian.org|g'

# ─── base image ─────────────────────────────────────────────────────────
RUN set -e; \
    apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        curl ca-certificates tini git tmux ${EXTRA_APT} && \
        apt-get clean && rm -rf /var/lib/apt/lists/*

# ─── uv installer ───────────────────────────────────────────────────────
ADD --chmod=755 https://astral.sh/uv/0.7.10/install.sh /install-uv.sh
RUN /install-uv.sh && rm /install-uv.sh
# $HOME isn’t defined at parse-time
ENV PATH=/root/.local/bin:$PATH      

# ─── Playwright + Chromium ──────────────────────────────────────────────
RUN uv pip install --system --no-cache-dir "playwright==${PLAYWRIGHT_VERSION}" && \
    mkdir -p /ms-playwright && chmod 0755 /ms-playwright && \
    playwright install --with-deps chromium && \
    chmod -R a+rX /ms-playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright


# ─── isolated venv ──────────────────────────────────────────────────────
RUN uv venv --python python /opt/venv
# keeps /root/.local/bin via shell expansion
ENV PATH=/opt/venv/bin:$PATH         

# ─── Olive wheel (staged under .olive/sandbox/.build) ───────────────────
COPY .olive/sandbox/.build/olive*.whl /tmp/wheels/
RUN set -e; \
    # 1) try highest-version wheel
    OLV_WHL=$(ls -1 /tmp/wheels/olive*.whl 2>/dev/null | sort -V | tail -n1); \
    # 2) if none, fall back to most-recent mtime
    [ -n "$OLV_WHL" ] || \
        OLV_WHL=$(ls -1t /tmp/wheels/olive*.whl 2>/dev/null | head -n1); \
    # 3) hard-fail if still nothing
    [ -n "$OLV_WHL" ] || { echo "No olive wheel found" >&2; exit 1; }; \
    # 4) install
    uv pip install --no-cache-dir "${OLV_WHL}"

# ─── project source (only used in copy-mode) ────────────────────────────
#TODO: Enable copy mode. for now this will give ENOSPC disk full junk
#WORKDIR /opt/app
#COPY . /mnt/project
RUN mkdir -p /mnt/project


# ─── non-root runtime user ──────────────────────────────────────────────
# Ensure the paths we’re about to chown exist in both mount- and copy-modes
RUN set -e; \
    useradd --create-home --shell /bin/bash olive; \
    mkdir -p /opt/app /mnt/project; \
    chown -R olive:olive /opt/venv /opt/app /mnt/project
USER olive
WORKDIR /home/olive

# keep PROJECT_ROOT env pointing at bind/volume mount
ENV PROJECT_ROOT=/mnt/project
# disables nested sandbox detection
ENV IS_OLIVE_SANDBOX=1     

# ─── entrypoint ─────────────────────────────────────────────────────────
COPY .olive/sandbox/entrypoint.sh /usr/local/bin/entrypoint.sh
ENTRYPOINT ["tini","--","bash","/usr/local/bin/entrypoint.sh"]

