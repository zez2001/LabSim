#!/usr/bin/env bash
set -euo pipefail
demo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd -- "$demo_dir/../.." && pwd)"
python_bin="${LABSIM_PYTHON:-$(dirname -- "$repo_dir")/labutopia-env/bin/python}"
export OMNI_KIT_ACCEPT_EULA=YES
exec "$python_bin" "$demo_dir/pipeline.py" "$@"
