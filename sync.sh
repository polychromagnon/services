#!/bin/bash
# Link every Finder Quick Action of this folder into ~/Library/Services: macOS then runs
# the copy kept here, so an edit here applies at once and stays reviewable in git.
# Run by maj on every pass; when everything is already linked it changes no link.
# No "menu:" header on purpose: the Shortcut launcher must never list this folder.
#
# Duplicates in ~/Library/Services are cleaned on the way:
#   - a link into the scripts folder whose target no longer exists is removed;
#   - a real copy (not a link) whose every file git already holds is removed, which
#     also catches the old copy of a renamed action; nothing is lost, git keeps it;
#   - a link of the same name pointing elsewhere is replaced;
#   - a real copy of the same name that git does not hold is left alone and reported.
#   - the Claude app's three actions (Claude - ask/codeHere/send) are never touched.
set -u

HERE=$(cd "$(dirname "$0")" && pwd)
SCRIPTS=$(dirname "$HERE")
LIB="$HOME/Library/Services"
BREW=/opt/homebrew/bin/brew
problems=0

# The actions call these Homebrew tools by full path: install whichever is missing.
for t in qpdf img2pdf exiftool mozjpeg; do
  p=/opt/homebrew/bin/$t
  [ "$t" = mozjpeg ] && p=/opt/homebrew/opt/mozjpeg/bin/cjpeg  # keg-only: never in bin
  [ -x "$p" ] && continue
  if [ -x "$BREW" ] && "$BREW" install "$t"; then
    continue
  fi
  echo "Clics droits : $t manque et n'a pas pu être installé (brew install $t)." >&2
  problems=1
done

# True when git already stores the exact content of every file of folder $1.
saved_in_git() {
  local f h
  while IFS= read -r -d '' f; do
    h=$(git hash-object -- "$f")
    # services has its own repo since 2026-11-05; older contents stay in the scripts repo
    git -C "$HERE" cat-file -e "$h" 2>/dev/null || git -C "$SCRIPTS" cat-file -e "$h" 2>/dev/null || return 1
  done < <(find "$1" -type f ! -name .DS_Store -print0)
}

mkdir -p "$LIB"

# Duplicates: links left behind by a renamed or moved action, and real copies git holds.
for dst in "$LIB"/*.workflow; do
  case "$(basename -- "$dst")" in
    # The Claude app's own actions stay out, whatever git knows of their files.
    "Claude - ask.workflow"|"Claude - codeHere.workflow"|"Claude - send.workflow") continue ;;
  esac
  if [ -L "$dst" ]; then
    target=$(readlink "$dst")
    case "$target" in
      "$SCRIPTS"/*)
        if [ ! -e "$target" ]; then
          rm -f -- "$dst"
          echo "Clics droits : ancien lien retiré, $(basename -- "$dst")"
        fi
        ;;
    esac
  elif [ -d "$dst" ] && saved_in_git "$dst"; then
    rm -rf -- "$dst"
    echo "Clics droits : doublon retiré (git le garde), $(basename -- "$dst")"
  fi
done

for src in "$HERE"/*.workflow; do
  [ -d "$src" ] || continue
  name=$(basename -- "$src")
  dst="$LIB/$name"
  if [ -L "$dst" ]; then
    [ "$(readlink "$dst")" = "$src" ] && continue
    rm -f -- "$dst"
  elif [ -e "$dst" ]; then
    echo "Clics droits : « $name » existe déjà dans ~/Library/Services avec un contenu que git n'a pas, il n'est pas remplacé. Demande à Claude de le comparer à scripts/services avant de le supprimer." >&2
    problems=1
    continue
  fi
  ln -s "$src" "$dst"
  echo "Clics droits : relié, $name"
done

# Rebuild the Services menu on every pass: macOS watches ~/Library/Services, not the
# linked folders, so an Info.plist edit here (menu name, file types) shows only after this.
/System/Library/CoreServices/pbs -flush 2>/dev/null || true
exit "$problems"
