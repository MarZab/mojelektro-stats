#!/bin/sh
#MISE description="Plan, create, or run this project's sandbox as its manager does"
#MISE alias="sandbox"
# Usage: tools/sandbox/run.sh [plan|create|run|rm] [sbx flags...]   (default: plan)
#   plan    what the files would change; changes nothing
#   create  make the sandbox; fails when one of that name exists (rm it first)
#   run     create it if needed and attach
#   rm      remove it
# It uses the name in sbxenv.yaml and, when it exists, the overlay the manager keeps in
# ~/.config/paddock/projects/NAME.sbxenv.yaml, so the sandbox is the one it would create.
# create passes --force, which only approves sbx's plan without asking; it never replaces a sandbox.
# RUN_SANDBOX_NAME=other tries the files under another name. RUN_SANDBOX_OVERLAY=FILE picks another
# overlay; empty means none.
# Nothing from the files runs on this Mac (--skip-host-commands).
# A mise file task as well: with `[task_config] includes = ["tools/sandbox"]` in mise.toml,
# `mise tasks` lists it and `mise run` runs it, arguments after `--`.
set -eu
cd "$(dirname "$0")/../.."
cmd="${1:-plan}"
[ "$#" -gt 0 ] && shift
name="${RUN_SANDBOX_NAME:-$(sed -n 's/^name: *"\{0,1\}\([^"]*\)"\{0,1\} *$/\1/p' sbxenv.yaml | head -n 1)}"
[ -n "$name" ] || { echo "no name: in sbxenv.yaml; set RUN_SANDBOX_NAME" >&2; exit 1; }
overlay="${RUN_SANDBOX_OVERLAY-${XDG_CONFIG_HOME:-$HOME/.config}/paddock/projects/$name.sbxenv.yaml}"
# What follows the command goes to sbx as it is (rm --force, for one), then the files.
if [ -f "$overlay" ]; then set -- "$@" sbxenv.yaml "$overlay"; files="sbxenv.yaml $overlay"; else set -- "$@" sbxenv.yaml; files=sbxenv.yaml; fi
echo "sandbox $name from: $files" >&2
case "$cmd" in
  plan) sbx env plan "$@" --name "$name" ;;
  create) sbx env create "$@" --name "$name" --skip-host-commands --force ;;
  run) sbx env run "$@" --name "$name" --skip-host-commands ;;
  rm) sbx env rm "$@" --name "$name" ;;
  *) echo "usage: $0 plan|create|run|rm" >&2; exit 2 ;;
esac
