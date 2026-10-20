#!/bin/bash
# Self-check of the "Créer un PDF" Quick Action on this Mac. It builds throwaway PDFs and
# images in a temporary folder, runs the workflow's own script on them with the same bare
# PATH as the Finder, and prints one line per check. Nothing outside that folder is
# touched; the action's dialogs are logged instead of shown.
# Run: bash creer-pdf/test-mac.sh, then send back everything it prints.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
WF="$HERE/Créer un PDF.workflow/Contents/document.wflow"
QPDF=/opt/homebrew/bin/qpdf
IMG2PDF=/opt/homebrew/bin/img2pdf
EXIFTOOL=/opt/homebrew/bin/exiftool
T=$(mktemp -d)
IN="$T/in"
mkdir -p "$IN" "$T/bin"
okn=0
kon=0
ok() { echo "OK     $1"; okn=$((okn + 1)); }
ko() { echo "ÉCHEC  $1"; kon=$((kon + 1)); }
note() { echo "INFO   $1"; }
have() { # FILE... : true when every fixture exists, else says which one is missing
  for x in "$@"; do [ -s "$x" ] || { note "essai sauté, fichier d'essai non fabriqué : $(basename "$x")"; return 1; }; done
}

for t in "$QPDF" "$IMG2PDF"; do
  [ -x "$t" ] || { echo "Manque $t : lance d'abord creer-pdf-clic-droit.sh"; exit 1; }
done
# img2pdf's own Python has Pillow: it draws the test pictures.
PY=$(head -n 1 "$IMG2PDF" | sed 's/^#! *//')
"$PY" -c "import PIL" 2>/dev/null || { echo "Python d'img2pdf introuvable ($PY)."; exit 1; }

plutil -extract actions.0.action.ActionParameters.COMMAND_STRING raw -o "$T/run.sh" "$WF" ||
  { echo "Impossible d'extraire le script du workflow."; exit 1; }

# Stand-in osascript: dialogs go to a log, the date-setting JXA goes to the real one.
cat >"$T/bin/osascript" <<'EOF'
#!/bin/bash
if [ "$1" = "-l" ]; then exec /usr/bin/osascript "$@"; fi
cat >/dev/null
printf '%s\n' "$2" >>"$DIALOGS"
EOF
chmod +x "$T/bin/osascript"

# run LOGNAME FILE... : runs the action like the Finder does, dialogs logged to $T/LOGNAME.log
run() {
  local log="$T/$1.log"
  shift
  : >"$log"
  DIALOGS="$log" PATH="$T/bin:${FINDER_PATH:-/usr/bin:/bin:/usr/sbin:/sbin}" /bin/bash "$T/run.sh" "$@"
}
said() { tr '\n' ' ' <"$T/$1.log"; }

# pages PDF : one line per page, "pageobject imageobject WxH" ("- none" without image)
pages() {
  "$QPDF" --show-pages --with-images "$1" | awk '
    /^page /{ if (p) print p, img, dim; p=$3; img="-"; dim="none"; next }
    / [0-9]+ 0 R, [0-9]+ x [0-9]+$/ && img=="-" { img=$2; d=$0; sub(/.*R, /,"",d); gsub(/ /,"",d); dim=d }
    END { if (p) print p, img, dim }'
}
dims() { pages "$1" | awk '{printf "%s ", $3}'; }
# upright PDF : "portrait" or "paysage", as the first page is displayed (image size + /Rotate)
upright() {
  local line w h rot
  line=$(pages "$1" | head -n 1)
  w=$(echo "$line" | awk '{split($3,a,"x"); print a[1]}')
  h=$(echo "$line" | awk '{split($3,a,"x"); print a[2]}')
  rot=$("$QPDF" --show-object="$(echo "$line" | awk '{print $1}')" "$1" | sed -n 's/.*\/Rotate \(-*[0-9]*\).*/\1/p')
  case "${rot:-0}" in 90 | 270 | -90 | -270) local x=$w; w=$h; h=$x ;; esac
  [ "$h" -gt "$w" ] && echo portrait || echo paysage
}

# --- Fixtures ------------------------------------------------------------------------------
"$PY" - "$IN" "$T" <<'PYEOF'
import sys
from PIL import Image, ImageDraw
d, t = sys.argv[1], sys.argv[2]
def pic(w, h, mode="RGB"):
    im = Image.new(mode, (w, h), (40, 110, 200) if mode == "RGB" else (40, 110, 200, 128))
    ImageDraw.Draw(im).rectangle((0, 0, w // 4, h // 4), fill=(230, 60, 40) if mode == "RGB" else (230, 60, 40, 255))
    return im
def exif(o):
    e = Image.Exif(); e[274] = o; return e
pic(600, 400).save(f"{t}/p1.png"); pic(610, 400).save(f"{t}/p2.png"); pic(620, 400).save(f"{t}/p3.png")
pic(630, 420).save(f"{d}/photo.jpg", quality=92, exif=exif(6))            # portrait phone photo
pic(650, 400).save(f"{d}/scan.tif", save_all=True, append_images=[pic(660, 400)], compression="tiff_lzw")
pic(670, 400, "RGBA").save(f"{d}/alpha.png")                              # real transparency
pic(680, 400).save(f"{d}/anim.gif", save_all=True, append_images=[pic(680, 400).rotate(180)], duration=200)
pic(690, 400).save(f"{d}/w.webp", lossless=True)
pic(60, 40).save(f"{d}/portrait.tif", tiffinfo={274: 6})                  # TIFF stored landscape, tag 6
pic(70, 40).save(f"{d}/miroir.jpg", exif=exif(5))                          # mirrored orientation
pic(80, 40).save(f"{t}/heicsrc.jpg", exif=exif(6))
Image.new("I;16", (50, 30), 30000).save(f"{d}/gris16.png")                # 16-bit PNG: kept as is
Image.new("I;16", (50, 30), 30000).save(f"{d}/gris16.tif")                # 16-bit TIFF: refused
PYEOF
"$IMG2PDF" -o "$IN/Facture d'été.pdf" "$T/p1.png" "$T/p2.png" 2>/dev/null # 2 pages
"$IMG2PDF" -o "$T/b0.pdf" "$T/p3.png" 2>/dev/null
"$QPDF" --object-streams=generate "$T/b0.pdf" "$IN/b.pdf"                  # 1 page, object streams
sips -s format heic "$T/heicsrc.jpg" --out "$IN/iphone.heic" >/dev/null 2>&1
[ -s "$IN/iphone.heic" ] && cp "$IN/iphone.heic" "$IN/vrai-heic.jpg"     # a HEIC misnamed .jpg
"$QPDF" --encrypt secret secret 256 -- "$IN/b.pdf" "$IN/verrou.pdf"
printf '<?xml version="1.0"?><Invoice/>' >"$T/factur-x.xml"
"$QPDF" --add-attachment "$T/factur-x.xml" -- "$IN/b.pdf" "$IN/facture.pdf"

# Dates as in the request: the first file at 11:05, the others at 11:06, one older creation.
for f in "$IN"/*; do touch -t 202510041106 "$f"; done
touch -t 202510041105 "$IN/Facture d'été.pdf"
touch -t 202001011200 "$IN/alpha.png" && touch -t 202510041107 "$IN/alpha.png"
ls "$IN" >"$T/names"
sums() { while IFS= read -r n; do printf '%s %s\n' "$(cksum <"$IN/$n")" "$n"; done <"$T/names"; }
before=$(sums)

# --- Case 1: the full mix, accented first name ------------------------------------------------
if have "$IN/Facture d'été.pdf" "$IN/photo.jpg" "$IN/b.pdf" "$IN/scan.tif" "$IN/alpha.png" "$IN/anim.gif" "$IN/w.webp"; then
  set -- "$IN/Facture d'été.pdf" "$IN/photo.jpg" "$IN/b.pdf" "$IN/scan.tif" "$IN/alpha.png" "$IN/anim.gif" "$IN/w.webp"
  run mix "$@"
  out="$IN/Facture d'été 2.pdf"
  if [ -f "$out" ]; then
    ok "PDF créé avec le nom attendu : $(basename "$out")"
    want="600x400 610x400 630x420 620x400 650x400 660x400 670x400 680x400 690x400 "
    got=$(dims "$out")
    [ "$got" = "$want" ] && ok "pages dans l'ordre de la sélection, une seule page pour le GIF animé ($("$QPDF" --show-npages "$out") pages)" ||
      ko "ordre ou nombre de pages : attendu [$want], obtenu [$got]"
    jimg=$(pages "$out" | awk 'NR==3{print $2}')
    "$QPDF" --show-object="$jimg" --raw-stream-data "$out" | cmp -s - "$IN/photo.jpg" &&
      ok "photo JPEG insérée octet pour octet" || ko "photo JPEG réencodée"
    # Every stream of the source PDF page (image and drawing instructions) must be identical.
    same=1
    for k in $("$QPDF" --show-pages "$IN/b.pdf" | awk '/^ *[0-9]+ 0 R$/{print $1}') $(pages "$IN/b.pdf" | awk '{print $2}'); do
      "$QPDF" --show-object="$k" --raw-stream-data "$IN/b.pdf" >"$T/s.bin" 2>/dev/null
      found=0
      for o in $("$QPDF" --show-pages "$out" | awk '/^ *[0-9]+ 0 R$/{print $1}') $(pages "$out" | awk '{print $2}'); do
        [ "$o" = "-" ] && continue
        "$QPDF" --show-object="$o" --raw-stream-data "$out" 2>/dev/null | cmp -s - "$T/s.bin" && { found=1; break; }
      done
      [ "$found" -eq 1 ] || same=0
    done
    [ "$same" -eq 1 ] && ok "page de PDF recopiée octet pour octet (image et dessin)" || ko "page de PDF modifiée"
    jp=$(pages "$out" | awk 'NR==3{print $1}')
    "$QPDF" --show-object="$jp" "$out" | grep -q '/Rotate 90' && ok "photo JPEG en portrait redressée (/Rotate 90)" ||
      ko "photo JPEG en portrait non redressée"

    minb=""
    minm=""
    for f in "$@"; do
      b=$(stat -f %B "$f")
      m=$(stat -f %m "$f")
      { [ -z "$minb" ] || [ "$b" -lt "$minb" ]; } && minb=$b
      { [ -z "$minm" ] || [ "$m" -lt "$minm" ]; } && minm=$m
    done
    fmt() { date -r "$1" "+%d/%m/%Y %H:%M:%S"; }
    [ "$(stat -f %m "$out")" = "$minm" ] && ok "date de modification = la plus ancienne ($(fmt "$minm"))" ||
      ko "date de modification $(fmt "$(stat -f %m "$out")") au lieu de $(fmt "$minm")"
    [ "$(stat -f %B "$out")" = "$minb" ] && ok "date de création = la plus ancienne ($(fmt "$minb"))" ||
      ko "date de création $(fmt "$(stat -f %B "$out")") au lieu de $(fmt "$minb")"
    info=$("$QPDF" --show-object=trailer "$out" | sed -n 's/.*\/Info \([0-9][0-9]*\) 0 R.*/\1/p')
    idict=$("$QPDF" --show-object="$info" "$out" 2>/dev/null)
    case "$idict" in *"D:$(date -r "$minb" +%Y%m%d%H%M%S)"*) ok "date de création interne au PDF" ;; *) ko "date de création interne : $idict" ;; esac
    case "$idict" in *"D:$(date -r "$minm" +%Y%m%d%H%M%S)"*) ok "date de modification interne au PDF" ;; *) ko "date de modification interne : $idict" ;; esac
    [ -s "$T/mix.log" ] && ko "message affiché : $(said mix)" || ok "aucun message d'alerte"
    "$QPDF" --check "$out" >/dev/null 2>&1 && ok "qpdf --check : PDF sain" || ko "qpdf --check signale un problème"
  else
    ko "aucun PDF créé ; message : $(said mix)"
  fi
fi

# --- Case 2: same selection again, name already taken ------------------------------------------
run again "$IN/Facture d'été.pdf" "$IN/b.pdf"
[ -f "$IN/Facture d'été 3.pdf" ] && ok "deuxième passage : « Facture d'été 3.pdf », rien d'écrasé" ||
  ko "deuxième passage : « Facture d'été 3.pdf » absent ; message : $(said again)"

# --- Case 3: reversed order ---------------------------------------------------------------------
run reverse "$IN/b.pdf" "$IN/Facture d'été.pdf"
got=$(dims "$IN/b 2.pdf" 2>/dev/null)
[ "$got" = "620x400 600x400 610x400 " ] && ok "ordre inversé respecté" || ko "ordre inversé : obtenu [$got] ; message : $(said reverse)"

# --- Case 4: orientation, displayed upright exactly once -----------------------------------------
if have "$IN/portrait.tif"; then
  run tif "$IN/portrait.tif"
  [ -f "$IN/portrait.pdf" ] && [ "$(upright "$IN/portrait.pdf")" = portrait ] && ok "TIFF en portrait affiché droit" ||
    ko "TIFF en portrait affiché couché ou absent ; message : $(said tif)"
fi
if [ -s "$IN/iphone.heic" ]; then
  o=""
  [ -x "$EXIFTOOL" ] && o=$("$EXIFTOOL" -s3 -n -Orientation "$IN/iphone.heic" 2>/dev/null)
  if [ "$o" = "6" ]; then
    run heic "$IN/iphone.heic"
    [ -f "$IN/iphone.pdf" ] && [ "$(upright "$IN/iphone.pdf")" = portrait ] && ok "HEIC en portrait affiché droit" ||
      ko "HEIC en portrait affiché couché ou absent ; message : $(said heic)"
  else
    note "essai HEIC en portrait sauté : le HEIC d'essai n'a pas gardé son orientation (${o:-illisible})"
  fi
  run misnamed "$IN/vrai-heic.jpg"
  [ -f "$IN/vrai-heic.pdf" ] && ok "HEIC nommé .jpg : converti quand même" || ko "HEIC nommé .jpg : $(said misnamed)"
else
  note "sips ne sait pas écrire de HEIC ici : essais HEIC sautés"
fi
if have "$IN/miroir.jpg"; then
  run mirror "$IN/miroir.jpg"
  grep -q "miroir" "$T/mirror.log" && ok "orientation en miroir signalée" || ko "orientation en miroir non signalée : $(said mirror)"
fi

# --- Case 5: refusals -------------------------------------------------------------------------
if have "$IN/gris16.tif"; then
  run deep "$IN/gris16.tif" "$IN/b.pdf"
  [ ! -e "$IN/gris16.pdf" ] && grep -q "8 bits" "$T/deep.log" && ok "TIFF 16 bits refusé avec un message, aucun PDF" ||
    ko "TIFF 16 bits : $(said deep)"
fi
if have "$IN/gris16.png"; then
  run png16 "$IN/gris16.png"
  k=$(pages "$IN/gris16.pdf" 2>/dev/null | awk 'NR==1{print $2}')
  [ -n "$k" ] && "$QPDF" --show-object="$k" "$IN/gris16.pdf" | grep -q "/BitsPerComponent 16" && ok "PNG 16 bits gardé en 16 bits" ||
    ko "PNG 16 bits : $(said png16)"
fi
run locked "$IN/verrou.pdf" "$IN/b.pdf"
[ ! -e "$IN/verrou 2.pdf" ] && grep -q "mot de passe" "$T/locked.log" && ok "PDF protégé : refusé avec un message, aucun PDF" ||
  ko "PDF protégé : $(said locked)"

# --- Case 6: PDF with an attached file (Factur-X invoice) ----------------------------------------
run attach "$IN/facture.pdf" "$IN/b.pdf"
[ -f "$IN/facture 2.pdf" ] && grep -q "Factur-X" "$T/attach.log" && ok "pièce jointe : PDF créé et alerte « garde l'original »" ||
  ko "pièce jointe : $(said attach)"

# --- Originals untouched ------------------------------------------------------------------------
[ "$(sums)" = "$before" ] &&
  ok "fichiers d'origine inchangés" || ko "un fichier d'origine a changé"

echo
echo "Bilan : $okn OK, $kon ÉCHEC"
if [ "$kon" -eq 0 ]; then
  rm -rf "$T"
else
  echo "Fichiers d'essai gardés pour examen : $T"
fi
