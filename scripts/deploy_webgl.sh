#!/usr/bin/env bash
# Prepare a Unity WebGL build for GitHub Pages: copy it into a clone of the Pages repository and commit it as the only commit
# (a Unity build is tens of megabytes of binary files that do not delta, so keeping every deploy in history would grow the
# repository without bound). It does NOT push: the last line printed is the command to run.
#
#   scripts/deploy_webgl.sh <build dir> <Pages repository clone> [--branch NAME] ["reason"]
#
# The commit message is made from the build (`server_admin.py describe`): "Development build d2edc3c (dirty): 146 MB, parts TUT 2, FN 42" and a body with the
# repository commit it was made from, what it holds and when; the optional reason (what this deploy is for) goes in the body. The Pages repository keeps only its latest
# commit, so the record of each deploy is the release `server_admin.py publish` registers, whose note is the same subject line (and `--note`, the reason).
#
# Use a clone made only for this (never your Unity project folder: the script deletes every file of the clone's working tree).
# With the foraging repository itself, clone it again (git clone <url> ~/foraging-pages) and deploy to a separate branch
# (--branch gh-pages): main is not touched. Without --branch the branch the clone has checked out is rewritten.
#
# The build must be a release build made with StreamingAssets/online.json enabled (see docs/ONLINE_DATA_PLAN.md, "Deploying the game").
set -euo pipefail

usage="usage: deploy_webgl.sh <build dir> <pages repo clone> [--branch NAME] [reason]"
build="${1:?$usage}"
repo="${2:?$usage}"
shift 2
branch=""
if [ "${1:-}" = "--branch" ]; then branch="${2:?$usage}"; shift 2; fi
reason="${1:-}"

[ -f "$build/index.html" ] && [ -d "$build/Build" ] || { echo "$build is not a Unity WebGL build (no index.html and Build/)" >&2; exit 1; }
[ -d "$repo/.git" ] || { echo "$repo is not a git clone" >&2; exit 1; }
if [ -d "$repo/ProjectSettings" ] || [ -d "$repo/Assets" ]; then
  echo "$repo looks like a Unity project working tree; this script deletes the clone's files. Use a separate clone (git clone <url> <new folder>)." >&2
  exit 1
fi
if [ -n "$(git -C "$repo" status --porcelain)" ]; then echo "$repo has uncommitted changes" >&2; exit 1; fi
[ -f "$build/StreamingAssets/online.json" ] || { echo "the build has no StreamingAssets/online.json" >&2; exit 1; }
grep -q '"enabled": *true' "$build/StreamingAssets/online.json" || { echo "online.json in the build has enabled=false: the game would refuse to start. Set it true and rebuild." >&2; exit 1; }
if find "$build" -type f -size +100M | grep -q .; then
  echo "a file in the build exceeds GitHub's 100 MB limit:" >&2
  find "$build" -type f -size +100M >&2
  exit 1
fi
if ls "$build"/Build/*.br "$build"/Build/*.gz >/dev/null 2>&1; then
  echo "note: the build has .br/.gz files; GitHub Pages sends no Content-Encoding for them, so the build needs Decompression Fallback (Player Settings > Publishing)." >&2
fi

python="$(dirname "$0")/../venv/bin/python"; [ -x "$python" ] || python=python3
message="$("$python" "$(dirname "$0")/server_admin.py" describe --build "$build" ${reason:+--reason "$reason"})"

branch="${branch:-$(git -C "$repo" symbolic-ref --short HEAD)}"
git -C "$repo" checkout --quiet --orphan deploy-tmp
find "$repo" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$build"/. "$repo"/
python3 "$(dirname "$0")/patch_webgl_page.py" "$repo/index.html"      # fixed drawing buffer: see that script
touch "$repo/.nojekyll"
git -C "$repo" add -A
git -C "$repo" commit --quiet -m "$message"
git -C "$repo" branch -M "$branch"      # replaces the old local branch of that name by the new single-commit history
du -sh "$repo" --exclude=.git | tail -1
echo "ready; publish with:"
echo "  git -C $repo push --force origin $branch"
