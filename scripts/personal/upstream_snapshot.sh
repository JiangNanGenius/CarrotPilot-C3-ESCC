#!/usr/bin/env bash
set -euo pipefail

refs=(
  "https://github.com/ajouatom/openpilot.git c3-wip"
  "https://github.com/ajouatom/openpilot.git carrot-wip"
  "https://github.com/jixiexiaoge/openpilot.git CP"
  "https://github.com/jixiexiaoge/openpilot.git atune"
  "https://github.com/jixiexiaoge/openpilot.git master"
  "https://jihulab.com/fishop/openpilot.git cp"
  "https://jihulab.com/fishop/openpilot.git escc-cpv9"
  "https://github.com/dhvms/carrotpilot.git master"
)

for ref in "${refs[@]}"; do
  repo="${ref% *}"
  branch="${ref##* }"
  printf "%-46s %-12s " "$repo" "$branch"
  git ls-remote --heads "$repo" "$branch" | awk '{print $1}'
done
