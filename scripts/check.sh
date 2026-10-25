#!/usr/bin/env bash
# 完整校验：后端测试、前端测试、前端构建（prebuild 会顺带检查 i18n）。
set -euo pipefail
cd "$(dirname "$0")/.."

uv run pytest -q -p no:cacheprovider
cd frontend
npm test
npm run build
