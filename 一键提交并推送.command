#!/bin/bash
set -euo pipefail

# Finder 双击时也能找到常见位置的 Python 3。
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"
cd "$(dirname "$0")"

fail() {
    printf '\n%s\n' "$1" >&2
    exit 1
}

push=true
if [[ $# -eq 1 && $1 == --commit-only ]]; then
    push=false
elif [[ $# -ne 0 ]]; then
    fail "用法：$0 [--commit-only]"
fi

branch=master
[[ "$(git symbolic-ref --quiet --short HEAD)" == "$branch" ]] ||
    fail "请先切换到 $branch 分支，再运行此脚本。"
for state in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply sequencer; do
    [[ ! -e "$(git rev-parse --git-path "$state")" ]] ||
        fail 'Git 正在合并、变基或应用提交。请先完成当前操作。'
done
git diff --cached --quiet ||
    fail '暂存区已有改动。请先处理这些改动，避免把它们混入本次提交。'
if $push; then
    git remote get-url --push origin >/dev/null || fail '找不到远程仓库 origin。'
fi

printf '正在重建软件源索引……\n'
python3 scripts/build_repo.py || fail '索引生成失败，未提交或推送。'

# 只暂存发布所需的文件，包含 .deb 的新增、替换和删除。
git add -A -- ':(top,glob)*.deb' Release Packages Packages.gz Packages.bz2 \
    CydiaIcon.png make.sh scripts/build_repo.py 一键提交并推送.command

if git diff --cached --quiet; then
    printf '软件源没有新改动，无需提交。\n'
else
    git diff --cached --stat
    git commit -m '更新 Cydia 软件源' || fail '提交失败，未推送。请查看上方 Git 提示。'
fi

if ! $push; then
    printf '本次仅在本地提交，未推送。\n'
elif [[ "$(git rev-parse HEAD)" == "$(git rev-parse --verify --quiet "refs/remotes/origin/$branch" || true)" ]]; then
    printf '没有待推送的本地提交。\n'
else
    printf '正在推送到 origin/%s……\n' "$branch"
    git push origin "HEAD:refs/heads/$branch" ||
        fail '推送失败，本地提交仍然保留。请按上方 Git 提示处理后重试。'
    printf '已推送。等 GitHub Pages 部署完成后，在手机上刷新软件源。\n'
fi
