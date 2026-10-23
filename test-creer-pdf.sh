#!/bin/bash
# Self-check of the "Créer un PDF" Quick Action on this Mac. It builds throwaway PDFs and
# images in a temporary folder, runs the workflow's own script on them with the same bare
# PATH as the Finder, and prints one line per check. Nothing outside that folder is
# touched; the action's dialogs are logged instead of shown.
# Run: bash services/test-creer-pdf.sh, then send back everything it prints.
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
skn=0
note() { echo "INFO   $1"; case "$1" in *sauté*) skn=$((skn + 1)) ;; esac; }
have() { # FILE... : true when every fixture exists, else says which one is missing
  local x
  for x in "$@"; do [ -s "$x" ] || { note "essai sauté, fichier d'essai non fabriqué : $(basename "$x")"; return 1; }; done
}

for t in "$QPDF" "$IMG2PDF"; do
  [ -x "$t" ] || { echo "Manque $t : lance d'abord maj"; exit 1; }
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
  # The Finder hands a Quick Action no locale: the Terminal's is removed too.
  env -u LANG -u LC_ALL -u LC_CTYPE DIALOGS="$log" PATH="$T/bin:${FINDER_PATH:-/usr/bin:/bin:/usr/sbin:/sbin}" /bin/bash "$T/run.sh" "$@"
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
# samepage SRC OUT : every content stream of SRC's pages (at least 2) is in OUT, byte for byte
samepage() {
  local k o found c=0
  for k in $("$QPDF" --show-pages "$1" | awk '/^ *[0-9]+ 0 R$/{print $1}'); do
    c=$((c + 1))
    "$QPDF" --show-object="$k" --raw-stream-data "$1" >"$T/s.bin" 2>/dev/null
    found=0
    for o in $("$QPDF" --show-pages "$2" 2>/dev/null | awk '/^ *[0-9]+ 0 R$/{print $1}'); do
      "$QPDF" --show-object="$o" --raw-stream-data "$2" 2>/dev/null | cmp -s - "$T/s.bin" && { found=1; break; }
    done
    [ "$found" -eq 1 ] || return 1
  done
  [ "$c" -ge 2 ]
}
# jpegsame PDF JPEG : the first page's image is the JPEG file, byte for byte
jpegsame() {
  local k
  k=$(pages "$1" 2>/dev/null | awk 'NR==1{print $2}')
  [ -n "$k" ] && [ "$k" != "-" ] && "$QPDF" --show-object="$k" --raw-stream-data "$1" 2>/dev/null | cmp -s - "$2"
}
# mbox PDF : width and height of the first page, in whole points
mbox() {
  "$QPDF" --show-object="$(pages "$1" | awk 'NR==1{print $1}')" "$1" |
    sed -n 's/.*\/MediaBox *\[ *[-0-9.]* *[-0-9.]* *\([-0-9.]*\) *\([-0-9.]*\) *\].*/\1 \2/p' |
    LC_ALL=C awk '{printf "%d %d", $1 + 0.5, $2 + 0.5}' # macOS awk reads "146.94" as 146 in a French locale
}
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
Image.new("I;16", (50, 30), 30000).save(f"{d}/png16.png")                 # 16-bit PNG: kept as is
Image.new("I;16", (50, 30), 30000).save(f"{d}/gris16.tif")                # 16-bit TIFF: kept or refused
pg = [Image.new("I;16", (50, 30), v) for v in (1000, 40000)]
pg[0].save(f"{d}/multi16.tif", save_all=True, append_images=pg[1:])       # 2 pages of 16 bits: refused
fax = Image.new("1", (300, 200), 1)                                        # fax scan stored landscape, tag 6
dr = ImageDraw.Draw(fax)
dr.rectangle((10, 10, 120, 90), fill=0); dr.line((0, 0, 299, 199), fill=0); dr.ellipse((150, 40, 280, 180), outline=0)
fax.save(f"{d}/fax.tif", compression="group4", tiffinfo={274: 6}, dpi=(204, 98))  # standard fax resolution
fax.save(f"{d}/fax-sans-dpi.tif", compression="group4", tiffinfo={274: 6})  # no resolution at all
# Small palettes with a transparent color (img2pdf mislabels their mask) and a 1-bit one with a transparent color.
pal = Image.new("P", (40, 30), 1)
pal.putpalette([255, 0, 0, 0, 0, 255, 0, 160, 0, 250, 220, 0])
dp = ImageDraw.Draw(pal)
dp.rectangle((0, 0, 9, 9), fill=0); dp.rectangle((20, 0, 29, 9), fill=2); dp.rectangle((0, 20, 9, 29), fill=3)
pal.save(f"{d}/pal4.png", transparency=0, dpi=(150, 150)); pal.save(f"{d}/pal4.gif", transparency=0)
mono = Image.new("1", (40, 30), 1)
ImageDraw.Draw(mono).rectangle((0, 0, 9, 9), fill=0)
mono.save(f"{d}/mono-t.png", transparency=0)
pic(300, 200).save(f"{d}/rgb6.tif", compression="tiff_lzw", tiffinfo={274: 6}, dpi=(204, 98))  # color TIFF, turned, 204x98 dpi
# A PDF page drawn by two content streams, one uncompressed and one in ASCII85, with no xref table.
import base64
s1 = b"0 0 1 rg 10 10 80 80 re f\n"
s2 = base64.a85encode(b"1 0 0 rg 40 40 20 20 re f\n") + b"~>"
def obj(n, body):
    return b"%d 0 obj" % n + body + b"endobj\n"
def stream(n, data, extra=b""):
    return obj(n, b"<</Length %d%s>>stream\n" % (len(data), extra) + data + b"\nendstream ")
raw = (b"%PDF-1.4\n" + obj(1, b"<</Type/Catalog/Pages 2 0 R>>") + obj(2, b"<</Type/Pages/Kids[3 0 R]/Count 1>>")
       + obj(3, b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 100 100]/Contents[4 0 R 5 0 R]>>")
       + stream(4, s1) + stream(5, s2, b"/Filter/ASCII85Decode") + b"trailer<</Root 1 0 R/Size 6>>\n%EOF\n")
open(f"{d}/abime.pdf", "wb").write(raw)                                   # damaged: no xref, qpdf repairs it
Image.new("1", (14000, 13000), 1).save(f"{d}/geant.png")                  # 182 Mpx, above Pillow's limit
# Interlaced 16-bit color PNG (img2pdf would cut it to 8 bits without a word), written by hand: Pillow cannot write interlaced PNG.
import struct, zlib
def chunk(k, b): return struct.pack(">I", len(b)) + k + b + struct.pack(">I", zlib.crc32(k + b) & 0xffffffff)
def adam7(w, h, px):  # px(x, y) -> pixel bytes; returns the interlaced scanlines
    out = b""
    for x0, y0, dx, dy in ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)):
        for y in range(y0, h, dy):
            row = b"".join(px(x, y) for x in range(x0, w, dx))
            if row:
                out += b"\x00" + row
    return out
lace = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 16, 16, 2, 0, 0, 1))
        + chunk(b"IDAT", zlib.compress(adam7(16, 16, lambda x, y: struct.pack(">HHH", x * 4000 + y, y * 4000 + x, 30000 + x * y))))
        + chunk(b"IEND", b""))
open(f"{d}/entrelace16.png", "wb").write(lace)
open(f"{d}/entrelace16-bis.jpg", "wb").write(lace)                        # same file, misnamed
PYEOF
cp "$IN/portrait.tif" "$IN/portrait2.Tiff"                                  # odd case extension
# PDFs written by hand, then rebuilt by qpdf: one with a layer, one with a signature field.
pdfraw() { # FILE CATALOG_EXTRA PAGE_EXTRA OBJ4
  printf '%%PDF-1.5\n1 0 obj<</Type/Catalog/Pages 2 0 R%s>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]%s>>endobj\n4 0 obj%s endobj\ntrailer<</Root 1 0 R/Size 5>>\n%%%%EOF\n' "$2" "$3" "$4" >"$T/raw.pdf"
  "$QPDF" "$T/raw.pdf" "$1" 2>/dev/null
}
pdfraw "$IN/calques.pdf" "/OCProperties<</OCGs[4 0 R]/D<</Order[4 0 R]/OFF[4 0 R]>>>>" "" "<</Type/OCG/Name(Calque)>>"
pdfraw "$IN/signe.pdf" "/AcroForm<</Fields[4 0 R]/SigFlags 3>>" "/Annots[4 0 R]" "<</Type/Annot/Subtype/Widget/FT/Sig/T(Signature1)/Rect[0 0 50 20]/P 3 0 R>>"
"$IMG2PDF" -o "$IN/Facture d'été.pdf" "$T/p1.png" "$T/p2.png" 2>/dev/null # 2 pages
"$IMG2PDF" -o "$T/b0.pdf" "$T/p3.png" 2>/dev/null
"$QPDF" --object-streams=generate "$T/b0.pdf" "$IN/b.pdf"                  # 1 page, object streams
sips -s format heic "$T/heicsrc.jpg" --out "$IN/iphone.heic" >/dev/null 2>&1
[ -s "$IN/iphone.heic" ] && cp "$IN/iphone.heic" "$IN/vrai-heic.jpg"     # a HEIC misnamed .jpg
"$QPDF" --encrypt secret secret 256 -- "$IN/b.pdf" "$IN/verrou.pdf"
printf '<?xml version="1.0"?><Invoice/>' >"$T/factur-x.xml"
"$QPDF" --add-attachment "$T/factur-x.xml" -- "$IN/b.pdf" "$IN/facture.pdf"
cp "$IN/b.pdf" "$IN/b-sans-extension"                                       # a PDF without .pdf
cp "$IN/photo.jpg" "$IN/APPAREIL.JPG"                                       # a camera's upper case name
cp "$IN/photo.jpg" "$IN/photo-sans-extension"                               # a JPEG without extension
"$QPDF" --stream-data=preserve "$IN/abime.pdf" "$IN/brut.pdf" 2>/dev/null  # same page, repaired, streams kept

# Dates as in the request: the first file at 11:05, the others at 11:06, one older creation.
for f in "$IN"/*; do touch -t 202510041106 "$f"; done
touch -t 202510041105 "$IN/Facture d'été.pdf"
touch -t 202001011200 "$IN/alpha.png" && touch -t 202510041107 "$IN/alpha.png"
# A copied file: created after its last modification (birth 2025-06-01, modified 2024-01-01).
cp "$IN/b.pdf" "$IN/copie.pdf"
/usr/bin/osascript -l JavaScript - "$IN/copie.pdf" 1704106800 1748772000 <<'JXA' >/dev/null 2>&1
function run(argv) {
  ObjC.import('Foundation');
  const fm = $.NSFileManager.defaultManager;
  const at = (s) => $.NSDate.dateWithTimeIntervalSince1970(Number(s));
  fm.setAttributesOfItemAtPathError($.NSDictionary.dictionaryWithObjectForKey(at(argv[1]), 'NSFileModificationDate'), argv[0], null);
  fm.setAttributesOfItemAtPathError($.NSDictionary.dictionaryWithObjectForKey(at(argv[2]), 'NSFileCreationDate'), argv[0], null);
}
JXA
ls "$IN" >"$T/names"
sums() { while IFS= read -r n; do printf '%s %s %s %s\n' "$(cksum <"$IN/$n")" "$(stat -f %m "$IN/$n")" "$(stat -f %B "$IN/$n")" "$n"; done <"$T/names"; }
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
    # Expected dates computed by Python, time zone included, not by the action's own formula.
    pdfd() { "$PY" -c "import datetime,sys; s=datetime.datetime.fromtimestamp(int(sys.argv[1])).astimezone().strftime('%Y%m%d%H%M%S%z'); print('D:'+s[:17]+chr(39)+s[17:]+chr(39))" "$1"; }
    case "$idict" in *"$(pdfd "$minb")"*) ok "date de création interne au PDF, fuseau compris ($(pdfd "$minb"))" ;; *) ko "date de création interne : $idict" ;; esac
    case "$idict" in *"$(pdfd "$minm")"*) ok "date de modification interne au PDF, fuseau compris" ;; *) ko "date de modification interne : $idict" ;; esac
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
if have "$IN/portrait2.Tiff"; then
  run tif2 "$IN/portrait2.Tiff"
  [ -f "$IN/portrait2.pdf" ] && [ "$(upright "$IN/portrait2.pdf")" = portrait ] && ok "TIFF nommé .Tiff : affiché droit aussi" ||
    ko "TIFF nommé .Tiff affiché couché ou absent ; message : $(said tif2)"
fi
# A fax scan is copied without decoding: decode the page back and compare it, pixel by pixel,
# with the scan as an image viewer shows it.
if have "$IN/fax.tif"; then
  run fax "$IN/fax.tif"
  k=$(pages "$IN/fax.pdf" 2>/dev/null | awk 'NR==1{print $2}')
  if [ -n "$k" ]; then
    "$QPDF" --show-object="$k" --raw-stream-data "$IN/fax.pdf" >"$T/fax.bin"
    "$QPDF" --show-object="$k" "$IN/fax.pdf" >"$T/fax.dict"
    diffpx=$("$PY" - "$IN/fax.tif" "$T/fax.bin" "$T/fax.dict" <<'PYEOF'
import io, re, struct, sys
from PIL import Image, ImageOps
src, raw, dic = sys.argv[1], open(sys.argv[2], "rb").read(), open(sys.argv[3]).read()
if "CCITTFaxDecode" not in dic:
    print("flux non CCITT"); sys.exit()
w = int(re.search(r"/Columns (\d+)", dic).group(1)); h = int(re.search(r"/Rows (\d+)", dic).group(1))
black1 = "/BlackIs1 true" in dic
tags = [(256, 4, 1, w), (257, 4, 1, h), (258, 3, 1, 1), (259, 3, 1, 4), (262, 3, 1, 1 if black1 else 0),
        (273, 4, 1, 8 + 2 + 12 * 8 + 4), (278, 4, 1, h), (279, 4, 1, len(raw))]
ifd = struct.pack("<H", len(tags)) + b"".join(struct.pack("<HHII", *t) for t in tags) + struct.pack("<I", 0)
got = Image.open(io.BytesIO(b"II*\x00\x08\x00\x00\x00" + ifd + raw)).convert("L")
want = ImageOps.exif_transpose(Image.open(src)).convert("L")
if got.size != want.size:
    print("taille %sx%s au lieu de %sx%s" % (got.size + want.size)); sys.exit()
print(sum(a != b for a, b in zip(got.tobytes(), want.tobytes())))
PYEOF
)
    [ "$diffpx" = 0 ] && [ "$(upright "$IN/fax.pdf")" = portrait ] && ok "scan fax en portrait : redressé, identique pixel pour pixel" ||
      ko "scan fax en portrait : $diffpx pixels différents ou page couchée ; message : $(said fax)"
    # 300x200 px at 204x98 dpi, turned a quarter: 200 px at 98 dpi wide, 300 px at 204 dpi high.
    [ "$(mbox "$IN/fax.pdf")" = "147 106" ] && ok "scan fax en portrait : taille de page juste (résolution 204x98 tournée)" ||
      ko "scan fax en portrait : page de $(mbox "$IN/fax.pdf") points au lieu de 147 106"
  else
    ko "scan fax en portrait : aucun PDF ; message : $(said fax)"
  fi
fi
if have "$IN/fax-sans-dpi.tif"; then
  run fax0 "$IN/fax-sans-dpi.tif"
  # No resolution: 96 dpi, like any other TIFF, so 200x300 px give 150x225 points.
  [ "$(mbox "$IN/fax-sans-dpi.pdf" 2>/dev/null)" = "150 225" ] && ok "scan fax sans résolution : taille de page normale" ||
    ko "scan fax sans résolution : page de $(mbox "$IN/fax-sans-dpi.pdf" 2>/dev/null) points au lieu de 150 225 ; message : $(said fax0)"
fi
# Transparent small-palette PNG and GIF, 1-bit PNG with a transparent color: decode each page and its
# transparency mask back and compare them, pixel by pixel, with the source.
if have "$IN/pal4.png" "$IN/pal4.gif" "$IN/mono-t.png"; then
  run pal "$IN/pal4.png" "$IN/pal4.gif" "$IN/mono-t.png"
  n=0
  for src in pal4.png pal4.gif mono-t.png; do
    n=$((n + 1))
    k=$(pages "$IN/pal4.pdf" 2>/dev/null | awk -v n=$n 'NR==n{print $2}')
    r="aucune page"
    if [ -n "$k" ] && [ "$k" != "-" ]; then
      "$QPDF" --show-object="$k" "$IN/pal4.pdf" >"$T/pal.dict"
      "$QPDF" --show-object="$k" --filtered-stream-data "$IN/pal4.pdf" >"$T/pal.bin" 2>/dev/null
      m=$(sed -n 's/.*\/SMask \([0-9]*\) 0 R.*/\1/p' "$T/pal.dict")
      : >"$T/palm.dict"
      : >"$T/palm.bin"
      if [ -n "$m" ]; then
        "$QPDF" --show-object="$m" "$IN/pal4.pdf" >"$T/palm.dict"
        "$QPDF" --show-object="$m" --filtered-stream-data "$IN/pal4.pdf" >"$T/palm.bin" 2>/dev/null
      fi
      r=$("$PY" -W ignore - "$IN/$src" "$T/pal.dict" "$T/pal.bin" "$T/palm.dict" "$T/palm.bin" <<'PYEOF'
import re, sys
from PIL import Image
src, d, b, md, mb = sys.argv[1], open(sys.argv[2]).read(), open(sys.argv[3], "rb").read(), open(sys.argv[4]).read(), open(sys.argv[5], "rb").read()
want = Image.open(src).convert("RGBA")
w, h = want.size
if not md:
    print("transparence perdue"); sys.exit()
if "/DeviceRGB" not in d or "/BitsPerComponent 8" not in d or "/BitsPerComponent 8" not in md or len(b) != w * h * 3 or len(mb) != w * h:
    print("image ou masque inattendu (%s, %s)" % (" ".join(re.findall(r"/(?:ColorSpace|BitsPerComponent) \S+", d)), " ".join(re.findall(r"/BitsPerComponent \S+", md))))
    sys.exit()
got = Image.frombytes("RGB", (w, h), b)
got.putalpha(Image.frombytes("L", (w, h), mb))
# A fully transparent pixel shows nothing: its color does not count.
print(sum(1 for p, q in zip(got.getdata(), want.getdata()) if p != q and (p[3] or q[3])))
PYEOF
)
    fi
    [ "$r" = 0 ] && ok "transparence de $src gardée, identique pixel pour pixel" || ko "transparence de $src : $r ; message : $(said pal)"
  done
  # 40x30 px at 150 dpi: 19.2x14.4 points.
  [ "$(mbox "$IN/pal4.pdf" 2>/dev/null)" = "19 14" ] && ok "image à palette : résolution gardée" ||
    ko "image à palette : page de $(mbox "$IN/pal4.pdf" 2>/dev/null) points au lieu de 19 14"
fi
if have "$IN/rgb6.tif"; then
  run rgb6 "$IN/rgb6.tif"
  # Same sizes as the fax: 300x200 px at 204x98 dpi, turned a quarter.
  [ "$(mbox "$IN/rgb6.pdf" 2>/dev/null)" = "147 106" ] && [ "$(upright "$IN/rgb6.pdf")" = portrait ] &&
    ok "TIFF couleur en portrait, résolution 204x98 : droit, taille de page juste" ||
    ko "TIFF couleur en portrait, résolution 204x98 : page de $(mbox "$IN/rgb6.pdf" 2>/dev/null) points au lieu de 147 106 ; message : $(said rgb6)"
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
# A 16-bit TIFF either keeps its 16 bits (macOS rewrites it as a 16-bit PNG) or is refused:
# a PDF with fewer bits would be a silent loss.
if have "$IN/gris16.tif"; then
  run deep "$IN/gris16.tif" "$IN/b.pdf"
  k=$(pages "$IN/gris16.pdf" 2>/dev/null | awk 'NR==1{print $2}')
  if [ -n "$k" ]; then
    "$QPDF" --show-object="$k" "$IN/gris16.pdf" | grep -q "/BitsPerComponent 16" && ok "TIFF 16 bits gardé en 16 bits" ||
      ko "TIFF 16 bits réduit en silence : $("$QPDF" --show-object="$k" "$IN/gris16.pdf" | grep -o '/BitsPerComponent [0-9]*')"
  else
    grep -q "8 bits" "$T/deep.log" && ok "TIFF 16 bits refusé avec un message, aucun PDF (macOS ne l'a pas gardé en 16 bits)" ||
      ko "TIFF 16 bits : $(said deep)"
  fi
fi
if have "$IN/multi16.tif"; then
  run multi16 "$IN/multi16.tif"
  [ ! -e "$IN/multi16.pdf" ] && grep -q "8 bits" "$T/multi16.log" && ok "TIFF 16 bits de 2 pages refusé avec un message, aucun PDF" ||
    ko "TIFF 16 bits de 2 pages : $(said multi16)"
fi
for x in entrelace16.png entrelace16-bis.jpg; do
  if have "$IN/$x"; then
    run lace "$IN/$x"
    k=$(pages "$IN/${x%.*}.pdf" 2>/dev/null | awk 'NR==1{print $2}')
    if [ -n "$k" ]; then
      "$QPDF" --show-object="$k" "$IN/${x%.*}.pdf" | grep -q "/BitsPerComponent 16" && ok "PNG 16 bits entrelacé ($x) gardé en 16 bits" ||
        ko "PNG 16 bits entrelacé ($x) réduit en silence"
    else
      grep -q "entrelacé" "$T/lace.log" && ok "PNG 16 bits entrelacé ($x) refusé avec un message (macOS ne l'a pas gardé en 16 bits)" ||
        ko "PNG 16 bits entrelacé ($x) : $(said lace)"
    fi
  fi
done
if have "$IN/geant.png"; then
  run big "$IN/geant.png"
  [ "$("$QPDF" --show-npages "$IN/geant.pdf" 2>/dev/null)" = 1 ] && ok "image géante (182 millions de pixels) acceptée" ||
    ko "image géante : $(said big)"
fi
if have "$IN/png16.png"; then
  run png16 "$IN/png16.png"
  k=$(pages "$IN/png16.pdf" 2>/dev/null | awk 'NR==1{print $2}')
  [ -n "$k" ] && "$QPDF" --show-object="$k" "$IN/png16.pdf" | grep -q "/BitsPerComponent 16" && ok "PNG 16 bits gardé en 16 bits" ||
    ko "PNG 16 bits : $(said png16)"
fi
run locked "$IN/verrou.pdf" "$IN/b.pdf"
[ ! -e "$IN/verrou 2.pdf" ] && grep -q "mot de passe" "$T/locked.log" && ok "PDF protégé : refusé avec un message, aucun PDF" ||
  ko "PDF protégé : $(said locked)"

# --- Case 6: PDF with an attached file (Factur-X invoice) ----------------------------------------
run attach "$IN/facture.pdf" "$IN/b.pdf"
[ -f "$IN/facture 2.pdf" ] && grep -q "Factur-X" "$T/attach.log" && ok "pièce jointe : PDF créé et alerte « garde l'original »" ||
  ko "pièce jointe : $(said attach)"

# --- Case 7: layers, signature, PDF without extension, file created after its modification ------
if have "$IN/calques.pdf"; then
  run layers "$IN/calques.pdf" "$IN/b.pdf"
  [ -f "$IN/calques 2.pdf" ] && grep -q "calques" "$T/layers.log" && ok "calques : PDF créé et alerte" || ko "calques : $(said layers)"
fi
if have "$IN/signe.pdf"; then
  run sig "$IN/signe.pdf" "$IN/b.pdf"
  [ -f "$IN/signe 2.pdf" ] && grep -q "signature" "$T/sig.log" && ok "signature électronique : PDF créé et alerte" || ko "signature : $(said sig)"
fi
run noext "$IN/b-sans-extension"
[ "$("$QPDF" --show-npages "$IN/b-sans-extension.pdf" 2>/dev/null)" = 1 ] && ok "PDF sans extension .pdf : repris comme PDF" ||
  ko "PDF sans extension : $(said noext)"
if have "$IN/brut.pdf"; then
  run brut "$IN/brut.pdf"
  samepage "$IN/brut.pdf" "$IN/brut 2.pdf" && ok "flux non compressé et flux ASCII85 recopiés octet pour octet" ||
    ko "flux non compressé ou ASCII85 réécrit ; message : $(said brut)"
fi
if have "$IN/abime.pdf"; then
  run abime "$IN/abime.pdf" "$IN/b.pdf"
  [ "$("$QPDF" --show-npages "$IN/abime 2.pdf" 2>/dev/null)" = 2 ] && ok "PDF légèrement abîmé : réparé et repris" ||
    ko "PDF légèrement abîmé : $(said abime)"
fi
run upper "$IN/APPAREIL.JPG"
jpegsame "$IN/APPAREIL.pdf" "$IN/photo.jpg" && ok "photo nommée .JPG en majuscules : insérée octet pour octet" ||
  ko "photo nommée .JPG : réencodée ou absente ; message : $(said upper)"
run noextjpg "$IN/photo-sans-extension"
jpegsame "$IN/photo-sans-extension.pdf" "$IN/photo.jpg" && ok "photo JPEG sans extension : insérée octet pour octet" ||
  ko "photo JPEG sans extension : réencodée ou absente ; message : $(said noextjpg)"
cb=$(stat -f %B "$IN/copie.pdf")
cm=$(stat -f %m "$IN/copie.pdf")
if [ "$cb" -gt "$cm" ]; then
  run copied "$IN/copie.pdf"
  [ "$(stat -f %B "$IN/copie 2.pdf" 2>/dev/null)" = "$cb" ] && [ "$(stat -f %m "$IN/copie 2.pdf")" = "$cm" ] && [ ! -s "$T/copied.log" ] &&
    ok "fichier copié (créé après sa modification) : ses deux dates reprises telles quelles" ||
    ko "fichier copié : création $(stat -f %B "$IN/copie 2.pdf" 2>/dev/null) au lieu de $cb, modification $(stat -f %m "$IN/copie 2.pdf" 2>/dev/null) au lieu de $cm ; message : $(said copied)"
else
  note "essai du fichier copié sauté : macOS n'a pas gardé une création postérieure à la modification"
fi

# --- The real alert dialog compiles (it is only logged above) ----------------------------------
if [ -x /usr/bin/osacompile ]; then
  sed -n "/<<'AS'/,/^AS\$/p" "$T/run.sh" | sed '1d;$d' >"$T/warn.applescript"
  [ -s "$T/warn.applescript" ] && /usr/bin/osacompile -o "$T/warn.scpt" "$T/warn.applescript" 2>"$T/osa.err" &&
    ok "message d'alerte : AppleScript valide" || ko "message d'alerte : AppleScript invalide ($(cat "$T/osa.err"))"
else
  note "osacompile absent : essai de l'AppleScript du message sauté"
fi

# --- Originals untouched ------------------------------------------------------------------------
[ "$(sums)" = "$before" ] &&
  ok "fichiers d'origine inchangés, dates comprises" || ko "un fichier d'origine a changé"

echo
if [ "$skn" -eq 0 ]; then
  echo "Bilan : $okn OK, $kon ÉCHEC"
else
  echo "Bilan : $okn OK, $kon ÉCHEC, $skn essai(s) sauté(s), voir les lignes INFO"
fi
if [ "$kon" -eq 0 ]; then
  rm -rf "$T"
else
  echo "Fichiers d'essai gardés pour examen : $T"
fi
