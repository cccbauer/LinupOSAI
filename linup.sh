#!/bin/bash
# Launch Linup with the conda env "linup" (flet 0.80.5), regardless of any
# other venv/conda env that is active in the calling shell.
ENV_DIR="$(conda info --base)/envs/linup"
cd "$(dirname "$0")" || exit 1
unset VIRTUAL_ENV PYTHONHOME PYTHONPATH
exec env PATH="$ENV_DIR/bin:/usr/bin:/bin:/usr/sbin:/sbin" "$ENV_DIR/bin/flet" run main.py "$@"
