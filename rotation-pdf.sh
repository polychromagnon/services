#!/bin/bash
# Rotation PDF via qpdf, en preservant l'identite complete de chaque fichier.
# ROTATE_ANGLE doit etre exporte a "+90" ou "-90" avant l'appel de ce script.
# Arguments : un ou plusieurs chemins (fichiers PDF ou dossiers).

set -u

QPDF="/opt/homebrew/bin/qpdf"
LOCK_SUFFIX=".rotation-pdf-lock"

if [ -z "${ROTATE_ANGLE:-}" ]; then
  echo "ROTATE_ANGLE n'est pas defini." >&2
  exit 1
fi

if [ ! -x "$QPDF" ]; then
  echo "qpdf est introuvable a $QPDF. Installez-le avec : brew install qpdf" >&2
  exit 1
fi

successes=()
failures=()

# Verrou actuellement detenu, pour que le filet ci-dessous puisse le rendre si
# le script est interrompu. Vide quand aucun verrou n'est tenu.
current_lock=""
# Passe a 1 quand le verrou doit SURVIVRE a la fin du traitement : c'est le cas
# ou un fichier est reste dans un etat douteux et ou le dossier de verrou
# contient les copies qui permettent de le recuperer a la main.
keep_lock=0

# Filet : rendre le verrou si le script s'arrete au milieu (fermeture de session,
# Automator qui coupe l'action, Ctrl-C). Ce n'est PAS une reprise automatique
# d'un verrou abandonne — interdite ici, cf. acquire_lock — mais la liberation
# de son propre verrou par le processus qui le detient encore, ce qui est sur.
# Un arret brutal (kill -9, coupure de courant) echappe forcement a ce filet :
# le verrou reste alors, et c'est le comportement voulu.
cleanup_on_exit() {
  if [ -n "$current_lock" ] && [ "$keep_lock" -eq 0 ]; then
    rm -rf -- "$current_lock"
  fi
}
trap cleanup_on_exit EXIT
trap 'trap - EXIT; cleanup_on_exit; exit 130' INT TERM HUP

# Filet de derniere chance pour la date de creation. Avec l'ecriture en place
# (cf. process_pdf_locked) le fichier garde son inode, donc sa date de creation
# n'a aucune raison de bouger : cette fonction n'est appelee que si la
# verification apres coup montre malgre tout un ecart.
restore_creation_date() {
  local target="$1" epoch="$2"
  osascript - "$target" "$epoch" <<'APPLESCRIPT' >/dev/null 2>&1
use framework "Foundation"
on run argv
  set targetPath to item 1 of argv
  set epochSeconds to (item 2 of argv) as real
  set theURL to current application's |NSURL|'s fileURLWithPath:targetPath
  set theDate to current application's |NSDate|'s dateWithTimeIntervalSince1970:epochSeconds
  set theResult to theURL's setResourceValue:theDate forKey:(current application's NSURLCreationDateKey) |error|:(missing value)
  if theResult as boolean is false then error "restore failed"
end run
APPLESCRIPT
}

# Deux invocations lancees en meme temps sur le MEME fichier (double clic, clic
# droit repete) se marcheraient dessus. On serialise donc l'acces a chaque
# fichier avec un verrou : UNIQUEMENT "mkdir" (atomique au niveau du systeme de
# fichiers, POSIX). Aucune tentative de reprise automatique d'un verrou
# "abandonne" (detecter si le detenteur precedent a plante) : quatre tentatives
# successives de le faire correctement (age du verrou, puis PID+kill -0, puis
# renommage atomique avec revalidation) ont chacune fini par reintroduire, sous
# une forme differente, exactement la course que le verrou existe pour
# empecher. Aucune de ces tentatives n'a jamais reussi a etre prouvee sure ;
# "mkdir" seul, lui, ne l'a jamais mis en defaut. Consequence assumee : si une
# invocation est tuee brutalement en tenant le verrou, CE fichier reste bloque
# jusqu'a suppression manuelle du dossier "<fichier>.rotation-pdf-lock" a cote
# de lui — jamais de perte ou de corruption, seulement un blocage explicite et
# recuperable, conformement au principe absolu de la rubrique 1 : la surete
# prime toujours, quitte a sacrifier une automatisation.
#
# Le dossier de verrou sert aussi d'espace de travail : la version tournee et
# la sauvegarde de l'original y sont ecrites. Un seul objet parasite apparait
# donc a cote du fichier pendant l'operation, et le rendre efface tout.
acquire_lock() {
  local lockdir="$1"
  if mkdir -- "$lockdir" 2>/dev/null; then
    echo "$$" > "$lockdir/pid" 2>/dev/null
    return 0
  fi
  return 1
}

release_lock() {
  local lockdir="$1"
  rm -rf -- "$lockdir" 2>/dev/null
}

# Ce qui identifie un fichier pour le systeme : son volume et son inode. Deux
# chemins qui donnent la meme valeur designent le MEME fichier, meme s'ils ne
# se ressemblent pas. Repli sur le chemin absolu si la lecture echoue.
file_identity() {
  local p="$1" id d b
  id=$(stat -L -f '%d:%i' -- "$p" 2>/dev/null)
  if [ -n "$id" ]; then
    printf '%s\n' "$id"
    return 0
  fi
  d=$(dirname -- "$p")
  b=$(basename -- "$p")
  ( cd -- "$d" 2>/dev/null && printf '%s/%s\n' "$(pwd -P)" "$b" ) || printf '%s\n' "$p"
}

# Ajoute un fichier a la liste a traiter, sauf si ce MEME fichier y figure deja.
# Sans cette deduplication, un fichier atteint deux fois par la meme selection
# serait tourne deux fois, soit 180 degres au lieu de 90, sans le moindre
# avertissement. Trois facons d'y arriver, toutes couvertes ici parce que la
# comparaison porte sur l'identite systeme et non sur le chemin : le meme
# fichier designe deux fois ; un dossier ET un PDF qu'il contient, que le
# Finder laisse selectionner ensemble en vue Liste depliee ; deux liens (durs
# ou symboliques) qui menent au meme fichier.
add_target() {
  local candidate="$1" identity i=0
  identity=$(file_identity "$candidate")
  while [ "$i" -lt "${#target_ids[@]}" ]; do
    if [ "${target_ids[$i]}" = "$identity" ]; then
      return 0
    fi
    i=$((i + 1))
  done
  target_ids[${#target_ids[@]}]="$identity"
  targets[${#targets[@]}]="$candidate"
}

process_pdf() {
  local pdf="$1"
  local name
  name=$(basename -- "$pdf")

  if [ ! -f "$pdf" ]; then
    failures+=("$name : fichier introuvable")
    return
  fi

  # Un dossier en lecture seule (volume monte en lecture seule, permissions)
  # empeche de poser le verrou. Sans ce test, l'echec serait rapporte comme
  # "une autre rotation est deja en cours", diagnostic faux qui enverrait
  # chercher un dossier de verrou inexistant.
  local dir
  dir=$(dirname -- "$pdf")
  if [ ! -w "$dir" ]; then
    failures+=("$name : le dossier qui le contient est en lecture seule, rien n'a ete tente")
    return
  fi

  # Fichier verrouille dans le Finder ou en lecture seule : on refuse au lieu de
  # passer outre. L'ancienne methode le remplacait par un fichier neuf, ce qui
  # effacait justement la protection que l'utilisateur avait posee.
  if [ ! -w "$pdf" ]; then
    failures+=("$name : le fichier est verrouille ou en lecture seule, rien n'a ete tente")
    return
  fi

  local lockdir="${pdf}${LOCK_SUFFIX}"
  if ! acquire_lock "$lockdir"; then
    failures+=("$name : une autre rotation semble deja en cours sur ce fichier (si ce message persiste sans raison, supprimez le dossier ${name}${LOCK_SUFFIX} a cote du fichier)")
    return
  fi
  current_lock="$lockdir"
  keep_lock=0

  process_pdf_locked "$pdf" "$name" "$lockdir"

  if [ "$keep_lock" -eq 0 ]; then
    release_lock "$lockdir"
  fi
  current_lock=""
}

# Rotation d'un fichier, verrou deja pris.
#
# Le fichier d'origine n'est JAMAIS remplace : qpdf ecrit la version tournee a
# cote, puis son contenu est reecrit A L'INTERIEUR du fichier d'origine. Le
# fichier garde donc son identite systeme (inode), et avec elle tout ce qui y
# est attache et qu'un remplacement detruirait : date de creation, permissions,
# etiquettes du Finder, commentaire Spotlight, provenance, listes de controle
# d'acces, liens durs. C'est la raison d'etre de cette construction ; ne pas la
# remplacer par "qpdf --replace-input", qui remplace le fichier par un fichier
# neuf et perd tout cela (seule la date de creation etait alors rattrapee, a la
# main, par un aller-retour AppleScript).
#
# Contrepartie assumee : la reecriture en place n'est pas atomique. D'ou la
# sauvegarde prise juste avant, la verification octet par octet juste apres, et
# la restauration automatique en cas d'ecart.
process_pdf_locked() {
  local pdf="$1" name="$2" lockdir="$3"
  local rotated="$lockdir/version-tournee.pdf"
  local backup="$lockdir/copie-de-securite.pdf"
  local errfile="$lockdir/erreur.txt"

  local birth_before
  birth_before=$(stat -L -f %B -- "$pdf" 2>/dev/null)
  if [ -z "$birth_before" ]; then
    failures+=("$name : impossible de lire la date de creation")
    return
  fi

  # 1. Rotation vers un fichier neuf. L'original n'est pas touche de toute
  #    cette etape : s'il echoue quoi qu'il arrive, il n'y a rien a defaire.
  "$QPDF" --rotate="${ROTATE_ANGLE}" --compress-streams=n --preserve-unreferenced-resources \
    -- "$pdf" "$rotated" 2>"$errfile"
  local rc=$?

  if [ "$rc" -eq 3 ]; then
    # qpdf a reussi avec des avertissements (ex. fichier endommage qu'il a du
    # reconstruire). On refuse ce resultat incertain, pour qu'un fichier
    # abime echoue proprement plutot que d'etre repare en silence.
    local reason
    reason=$(head -n 1 "$errfile")
    failures+=("$name : fichier corrompu ou invalide ($reason)")
    return
  fi

  if [ "$rc" -ne 0 ]; then
    local reason
    reason=$(head -n 1 "$errfile")
    failures+=("$name : rotation echouee ($reason)")
    return
  fi

  if [ ! -s "$rotated" ]; then
    failures+=("$name : rotation echouee (qpdf n'a produit aucun fichier exploitable)")
    return
  fi

  # 2. Sauvegarde de l'original, avant la moindre ecriture. C'est le filet de
  #    l'etape 4 : si la reecriture en place casse au milieu, c'est cette copie
  #    qui remet le fichier d'aplomb.
  if ! cp -p -- "$pdf" "$backup" 2>>"$errfile"; then
    failures+=("$name : impossible de preparer la copie de securite, rien n'a ete modifie")
    return
  fi

  # 3. La version tournee porte provisoirement les dates de l'original, pour
  #    pouvoir les lui rendre a l'etape 6 (l'ecriture en place change la date
  #    de modification, la seule que l'inode ne protege pas).
  touch -r "$pdf" -- "$rotated" 2>/dev/null

  # 4. Reecriture du contenu A L'INTERIEUR du fichier d'origine.
  if ! cat -- "$rotated" > "$pdf" 2>>"$errfile"; then
    restore_from_backup "$pdf" "$name" "$backup" "$lockdir" "ecriture impossible (disque plein ?)"
    return
  fi

  # 5. Verification octet par octet de ce qui a reellement ete ecrit.
  if ! cmp -s -- "$rotated" "$pdf"; then
    restore_from_backup "$pdf" "$name" "$backup" "$lockdir" "le fichier ecrit ne correspond pas a la version tournee"
    return
  fi

  # 6. Dates rendues a l'identique, puis controle de la date de creation.
  touch -r "$rotated" -- "$pdf" 2>/dev/null

  local birth_after
  birth_after=$(stat -L -f %B -- "$pdf" 2>/dev/null)
  if [ "$birth_after" != "$birth_before" ]; then
    # Ne devrait jamais arriver : l'inode n'a pas change. Filet malgre tout,
    # sauf si la date lue est nulle ou absurde — la reappliquer telle quelle
    # daterait le fichier du 1er janvier 1970.
    case "$birth_before" in
      ''|*[!0-9]*) : ;;
      0) : ;;
      *) restore_creation_date "$pdf" "$birth_before" ;;
    esac
    birth_after=$(stat -L -f %B -- "$pdf" 2>/dev/null)
    if [ "$birth_after" != "$birth_before" ]; then
      failures+=("$name : rotation appliquee mais la date de creation a change")
      return
    fi
  fi

  successes+=("$name")
}

# Remet le fichier dans son etat d'origine apres un incident d'ecriture. Si la
# remise en etat elle-meme echoue, le verrou est CONSERVE : il contient la copie
# de securite et la version tournee, et le message dit ou les trouver.
restore_from_backup() {
  local pdf="$1" name="$2" backup="$3" lockdir="$4" reason="$5"

  if cat -- "$backup" > "$pdf" 2>/dev/null && cmp -s -- "$backup" "$pdf"; then
    touch -r "$backup" -- "$pdf" 2>/dev/null
    failures+=("$name : $reason ; le fichier a ete remis a l'identique, aucune donnee perdue")
    return
  fi

  keep_lock=1
  failures+=("$name : $reason, ET la remise en etat a echoue. Le fichier d'origine intact se trouve dans le dossier ${name}${LOCK_SUFFIX} a cote de lui, sous le nom copie-de-securite.pdf ; la version tournee s'y trouve aussi sous le nom version-tournee.pdf. Remettez l'un des deux a la place du fichier, puis supprimez ce dossier.")
}

targets=()
target_ids=()
if [ "$#" -gt 0 ]; then
  for arg in "$@"; do
    if [ -d "$arg" ]; then
      while IFS= read -r -d '' pdf; do
        add_target "$pdf"
      done < <(find "$arg" -maxdepth 1 -type f -iname '*.pdf' -print0)
    elif [ -f "$arg" ]; then
      add_target "$arg"
    else
      failures+=("$(basename -- "$arg") : introuvable au moment du traitement")
    fi
  done
fi

# Un tableau vide developpe sous "set -u" est une erreur fatale sur le bash 3.2
# de macOS (bash 5 l'accepte). Le cas se produit des qu'aucun PDF n'est trouve,
# par exemple sur un dossier qui n'en contient aucun.
if [ "${#targets[@]}" -gt 0 ]; then
  for pdf in "${targets[@]}"; do
    process_pdf "$pdf"
  done
fi

total=$(( ${#successes[@]} + ${#failures[@]} ))

if [ "$total" -eq 0 ]; then
  exit 0
fi

if [ "$total" -eq 1 ] && [ "${#failures[@]}" -eq 0 ]; then
  exit 0
fi

message="Rotation PDF : ${#successes[@]} reussie(s), ${#failures[@]} echec(s)."
if [ "${#failures[@]}" -gt 0 ]; then
  message="${message}"$'\n\n'"Echecs :"
  for f in "${failures[@]}"; do
    message="${message}"$'\n'"- $f"
  done
fi

osascript - "$message" <<'APPLESCRIPT' >/dev/null 2>&1
on run argv
  display dialog (item 1 of argv) buttons {"OK"} default button "OK" with title "Rotation PDF"
end run
APPLESCRIPT

# Le code de sortie d'osascript n'est pas fiable a lui seul comme canal
# d'echec (contexte sans session UI, permission AppleScript refusee, etc.) :
# meme si le dialogue ci-dessus echoue en silence, le code de sortie de CE
# script doit refleter l'echec, pour que le filet natif d'Automator (deja
# utilise pour le cas qpdf absent) se declenche a defaut du dialogue.
if [ "${#failures[@]}" -gt 0 ]; then
  echo "$message" >&2
  exit 1
fi

exit 0
