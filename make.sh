#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
python3 scripts/build_repo.py
printf '\n索引已更新。请检查 git diff，再手动提交和推送；本脚本不会自动发布。\n'
