FROM ghcr.io/astral-sh/uv:python3.13-alpine@sha256:7b02bf9f2d812bf1b21b4d790901eb22250523943b82af93e8c543ea54b6b4d5 AS dependencies
WORKDIR /srv/campusclaw
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

FROM ghcr.io/astral-sh/uv:python3.13-alpine@sha256:7b02bf9f2d812bf1b21b4d790901eb22250523943b82af93e8c543ea54b6b4d5
WORKDIR /srv/campusclaw
ARG APP_BUILD_REVISION
RUN python -m pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.13/ensurepip \
    && rm -f /usr/local/bin/uv /usr/local/bin/uvx
COPY --from=dependencies /srv/campusclaw/.venv .venv
COPY app app
RUN python -c 'import re, sys; from pathlib import Path; revision = sys.argv[1]; assert re.fullmatch("[0-9a-f]{40}", revision), "APP_BUILD_REVISION"; Path("app/BUILD_VERSION").write_text(revision + "\n")' "$APP_BUILD_REVISION"
LABEL org.opencontainers.image.revision=$APP_BUILD_REVISION
ENV PATH="/srv/campusclaw/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "app"]
