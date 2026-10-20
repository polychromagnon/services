#!/bin/bash
# Link every Finder Quick Action of this folder into ~/Library/Services: macOS then runs
# the copy kept here, so an edit here applies at once and stays reviewable in git.
# Run by maj on every pass; when everything is already linked it changes nothing.
# No "menu:" header on purpose: the Shortcut launcher must never list this folder.
#
# Duplicates in ~/Library/Services are cleaned on the way:
#   - a link into the scripts folder whose target no longer exists is removed;
#   - a link of the same name pointing elsewhere is replaced;
#   - a real copy of the same name is replaced only if git already holds every one of
#     its files, so nothing is lost; otherwise it is left alone and reported.
set -u

HERE=$(cd "$(dirname "$0")" && pwd)
SCRIPTS=$(dirname "$HERE")
LIB="$HOME/Library/Services"
BREW=/opt/homebrew/bin/brew
changed=0
problems=0

# The actions call these Homebrew tools by full path: install whichever is missing.
for t in qpdf img2pdf; do
  [ -x "/opt/homebrew/bin/$t" ] && continue
  if [ -x "$BREW" ] && "$BREW" install "$t"; then
    continue
  fi
  echo "Clics droits : $t manque et n'a pas pu être installé (brew install $t)." >&2
  problems=1
done

# True when git already stores the exact content of every file of folder $1.
saved_in_git() {
  local f
  while IFS= read -r -d '' f; do
    git -C "$SCRIPTS" cat-file -e "$(git hash-object -- "$f")" 2>/dev/null || return 1
  done < <(find "$1" -type f ! -name .DS_Store -print0)
}

mkdir -p "$LIB"

# Links left behind by a renamed or moved action.
for dst in "$LIB"/*; do
  [ -L "$dst" ] || continue
  target=$(readlink "$dst")
  case "$target" in
    "$SCRIPTS"/*)
      if [ ! -e "$target" ]; then
        rm -f -- "$dst"
        echo "Clics droits : ancien lien retiré, $(basename -- "$dst")"
        changed=1
      fi
      ;;
  esac
done

for src in "$HERE"/*.workflow; do
  [ -d "$src" ] || continue
  name=$(basename -- "$src")
  dst="$LIB/$name"
  if [ -L "$dst" ]; then
    [ "$(readlink "$dst")" = "$src" ] && continue
    rm -f -- "$dst"
  elif [ -e "$dst" ]; then
    if ! saved_in_git "$dst"; then
      echo "Clics droits : « $name » existe déjà dans ~/Library/Services avec un contenu que git n'a pas, il n'est pas remplacé. Demande à Claude de le comparer à scripts/services avant de le supprimer." >&2
      problems=1
      continue
    fi
    rm -rf -- "$dst"
  fi
  ln -s "$src" "$dst"
  echo "Clics droits : relié, $name"
  changed=1
done

# Rebuild the Services menu now instead of waiting for macOS to notice the change.
if [ "$changed" -eq 1 ]; then
  /System/Library/CoreServices/pbs -flush 2>/dev/null || true
fi
exit "$problems"
