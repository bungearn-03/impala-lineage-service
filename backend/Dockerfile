# syntax=docker/dockerfile:1
FROM python:3.11-slim

# System build deps required to compile impyla/sasl/thrift-sasl from source
# on Debian-based images (they need a C compiler plus the Cyrus SASL and
# OpenSSL development headers).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libsasl2-dev \
        libssl-dev \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps as their own layer so code-only changes don't bust
# the (slow, C-extension-heavy) dependency install cache.
COPY requirements.txt .
# `thrift`'s optional C accelerator (thrift.protocol.fastbinary, compiled here
# since a C++ compiler is present) has a long-standing upstream bug: its
# module.cpp calls PyArg_ParseTuple/Py_BuildValue with '#' format codes
# without `#define PY_SSIZE_T_CLEAN` before `#include <Python.h>` in that
# file specifically (binary.cpp/compact.cpp do define it, module.cpp doesn't
# -- confirmed unfixed as of thrift 0.21.0, the newest release checked).
# Under Python 3.10+ this raises `SystemError: PY_SSIZE_T_CLEAN macro must
# be defined for '#' formats` at runtime the first time a HiveServer2/Impala
# RPC response is decoded -- i.e. on literally the first real query. Thrift
# already has a safe, well-tested pure-Python decode/encode path and uses it
# automatically whenever the C extension fails to import (see
# TBinaryProtocolAccelerated in thrift/protocol/TBinaryProtocol.py), so the
# simplest correct fix is to remove the broken compiled extension rather
# than patch or vendor thrift.
RUN pip install --no-cache-dir -r requirements.txt \
    && rm -f /usr/local/lib/python3.11/site-packages/thrift/protocol/fastbinary*.so

COPY app ./app
COPY scripts ./scripts

# database/migrations/env.py locates the app package via a path relative to
# its own file (../../backend), since on the host it's a sibling of backend/.
# That relationship doesn't exist inside this image (only /app and, when
# mounted, /migrations are present) -- so alembic run from /migrations can't
# find `app` on sys.path. Setting PYTHONPATH here makes `app` importable
# regardless of the current working directory, independent of env.py's
# host-oriented relative-path logic.
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
