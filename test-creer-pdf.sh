#!/bin/bash
# Self-test of the "Créer un PDF" Quick Action on this Mac. It builds throwaway PDFs and
# images in a temporary folder, runs the workflow's own script on them with the Finder's
# bare PATH, and prints one line per check. Nothing outside that folder is touched; the
# action's dialogs are logged instead of shown.
# Run: bash ~/Developer/scripts/services/test-creer-pdf.sh, then send back what it prints.
HERE=$(cd "$(dirname "$0")" && pwd)
PY=$(sed -n '1s/^#! *//p' /opt/homebrew/bin/img2pdf 2>/dev/null)
[ -x "$PY" ] || { echo "img2pdf introuvable : lance d'abord maj"; exit 1; }
T=$(mktemp -d)
trap 'chmod -R u+w "$T"; rm -rf "$T"' EXIT
mkdir "$T/bin"
plutil -extract actions.0.action.ActionParameters.COMMAND_STRING raw -o "$T/action.sh" \
  "$HERE/Créer un PDF.workflow/Contents/document.wflow" || { echo "Script du workflow illisible."; exit 1; }
# Stand-in osascript: dialogs go to a log, the date-setting JavaScript goes to the real one.
cat >"$T/bin/osascript" <<'EOF'
#!/bin/bash
[ "$1" = "-l" ] && exec /usr/bin/osascript "$@"
printf '%s\n' "${@: -1}" >>"$DIALOG_LOG"
EOF
chmod +x "$T/bin/osascript"
"$PY" -I - "$T" "$HERE" <<'PY'
import hashlib, io, os, re, shutil, struct, subprocess, sys, time, zlib
from datetime import datetime, timezone
import img2pdf, pikepdf, PIL
from PIL import Image, ImageCms, ImageOps

T = sys.argv[1]
oks = kos = 0
print(f"INFO   img2pdf {img2pdf.__version__}, pikepdf {pikepdf.__version__}, Pillow {PIL.__version__}, Python {sys.version.split()[0]}")


def check(cond, label):
    global oks, kos
    print(("OK     " if cond else "ÉCHEC  ") + label)
    oks, kos = oks + bool(cond), kos + (not cond)


def said(dialogs):
    return " ".join(dialogs.split())[:200]


def setdates(path, birth, mtime):
    os.utime(path, (mtime, mtime))
    subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", """function run(a) { ObjC.import('Foundation');
      $.NSFileManager.defaultManager.setAttributesOfItemAtPathError($.NSDictionary.dictionaryWithObjectForKey(
      $.NSDate.dateWithTimeIntervalSince1970(Number(a[1])), 'NSFileCreationDate'), a[0], null); }""",
                    path, str(birth)], capture_output=True)


def ts(s):
    return int(datetime.fromisoformat(s).timestamp())


def pattern(w=60, h=40, alpha=False):
    """Four colored quarters (to see a turn or a mirror) with fine noise (to see any loss)."""
    im = Image.new("RGBA" if alpha else "RGB", (w, h))
    for y in range(h):
        for x in range(w):
            q = [(220, 30, 30), (30, 200, 30), (30, 30, 220), (230, 220, 30)][(y >= h // 2) * 2 + (x >= w // 2)]
            px = tuple((c + (x * 7 + y * 13) % 9) % 256 for c in q)
            im.putpixel((x, y), px + ((x * 5 + y * 3) % 256,) if alpha else px)
    return im


def make_pdf(path, labels, info=None):
    pdf = pikepdf.new()
    for lab in labels:
        pdf.add_blank_page(page_size=(200, 100))
        pdf.pages[-1].Contents = pdf.make_stream(f"% {lab}\n0 0 m 150 80 l S\n".encode())
    if info:
        for k, v in info.items():
            pdf.docinfo[k] = v
    pdf.save(path)


def run(*files):
    log = os.path.join(T, "dialogs.txt")
    open(log, "w").close()
    folder = os.path.dirname(files[0])
    before = set(os.listdir(folder))
    t0 = time.time()
    r = subprocess.run(["/bin/bash", os.path.join(T, "action.sh"), *files], capture_output=True, text=True,
                       env={"PATH": f"{T}/bin:/usr/bin:/bin:/usr/sbin:/sbin", "DIALOG_LOG": log, "HOME": os.environ["HOME"]})
    new = sorted(set(os.listdir(folder)) - before)
    dialogs = open(log).read()
    if r.returncode:  # the action crashed: its last error line says why
        dialogs += "plantage : " + (r.stderr.strip().splitlines() or ["?"])[-1]
    return [os.path.join(folder, n) for n in new], dialogs, time.time() - t0


def heic(src, out):
    """Makes an iPhone-like HEIC with the Mac's own sips; says why when it cannot."""
    r = subprocess.run(["sips", "-s", "format", "heic", src, "--out", out], capture_output=True, text=True)
    if os.path.exists(out):
        return True
    check(False, f"HEIC : sips n'a pas pu fabriquer la photo d'essai ({said(r.stderr + r.stdout)})")
    return False


def icc(x):
    cs = x.get("/ColorSpace")
    return cs[1].read_bytes() if isinstance(cs, pikepdf.Array) and cs[0] == "/ICCBased" else b""


def first_image(page):
    xobjects = (page.obj.get("/Resources") or {}).get("/XObject") or {}
    return [v for _, v in xobjects.items() if v.get("/Subtype") == "/Image"][0]


def page_image(page):
    x = first_image(page)
    im = pikepdf.PdfImage(x).as_pil_image()
    if "/SMask" in x and im.mode not in ("RGBA", "LA"):
        im = im.convert("RGBA")
        im.putalpha(pikepdf.PdfImage(x.SMask).as_pil_image().convert("L"))
    rot = int(page.obj.get("/Rotate", 0)) % 360
    turn = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}
    return (im.transpose(turn[rot]) if rot else im), x, rot


def a4_wide(page, dots=1.0):
    """Shown as wide as an A4 sheet turned the same way (21 cm for a portrait or square image,
    29.7 cm for a landscape one; a turned page swaps its sides), as tall as its proportions."""
    mb = [float(v) for v in page.mediabox]
    w, h = (mb[2] - mb[0]) / 72 * 2.54, (mb[3] - mb[1]) / 72 * 2.54
    if int(page.obj.get("/Rotate", 0)) % 180:
        w, h = h, w
    im = page_image(page)[0]
    want = 21 if im.height * dots >= im.width else 29.7
    return abs(w - want) < 0.01 and abs(h - want * im.height / im.width * dots) < 0.05, f"{w:.1f} x {h:.1f} cm"


def same(a, b):
    mode = "RGBA" if "A" in a.mode + b.mode or "transparency" in b.info else "RGB"
    return a.size == b.size and a.convert(mode).tobytes() == b.convert(mode).tobytes()


# Michael's own iPhone photo, stored on its side ("Rotate 90 CW"), Display P3. Upright it is
# 3024 x 4032 and, averaged to 3 x 4 blocks, has these colors (checked by eye on the Mac;
# turned or mirrored, some block is 43 to 62 off, so 20 leaves room for the Mac's decoder).
PHOTO = os.path.normpath(os.path.join(sys.argv[2], "..", "test-HEIC", "img.heic"))
UPRIGHT = bytes.fromhex("6d6e6e969a9d797c7b666564a4a09d6f6f70685e53bb9e8280807e534f4b816e5f68696a")


def upright(im):
    blocks = im.convert("RGB").resize((3, 4), Image.Resampling.BOX).tobytes()
    return im.size == (3024, 4032) and all(abs(p - q) < 20 for p, q in zip(blocks, UPRIGHT))


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


D = os.path.join(T, "in")
os.mkdir(D)
srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
p3 = open("/System/Library/ColorSync/Profiles/Display P3.icc", "rb").read()  # the iPhone's color space
desc = lambda icc: ImageCms.getProfileDescription(ImageCms.ImageCmsProfile(io.BytesIO(icc)))
up = pattern()                      # what every photo must look like, upright
turned = up.transpose(Image.Transpose.ROTATE_90)  # stored on its side, EXIF says turn it back

# --- 1. Everyday mix: PDF, iPhone-like JPEG, screenshot, HEIC, PDF, in click order ---------
make_pdf(f"{D}/a.pdf", ["A1", "A2"], {"/CreationDate": "D:20200301100000+01'00'"})
make_pdf(f"{D}/b.pdf", ["B1"], {"/ModDate": "D:20180704120000Z"})
ex = Image.Exif()
ex[274] = 6
ex.get_ifd(0x8769).update({0x9003: "2019:05:12 14:03:22", 0x9011: "+02:00"})
turned.save(f"{D}/photo.jpg", quality=92, exif=ex, icc_profile=srgb)
pattern(alpha=True).save(f"{D}/capture.png")
has_heic = os.path.isfile(PHOTO)
if has_heic:
    shutil.copy(PHOTO, f"{D}/iphone.heic")
else:
    check(False, f"HEIC : photo d'essai introuvable ({PHOTO})")
mix = [f"{D}/a.pdf", f"{D}/photo.jpg", f"{D}/capture.png"] + [f"{D}/iphone.heic"] * has_heic + [f"{D}/b.pdf"]
pages = 5 + has_heic
for f in mix:
    setdates(f, ts("2023-01-01T10:00:00"), ts("2024-01-01T10:00:00"))
setdates(f"{D}/capture.png", ts("2021-06-01T08:00:00"), ts("2024-01-01T10:00:00"))
hashes = {f: (sha(f), os.stat(f).st_mtime) for f in mix}
out, dialogs, took = run(*mix)
check(len(out) == 1 and os.path.basename(out[0]) == "a 2.pdf", f"mélange : un seul PDF, nommé comme chez Apple ({[os.path.basename(o) for o in out]})")
check(dialogs == "", f"mélange : aucune alerte ({said(dialogs)})")
if out:
    with pikepdf.open(out[0]) as pdf, pikepdf.open(f"{D}/a.pdf") as a, pikepdf.open(f"{D}/b.pdf") as b:
        p = pdf.pages
        check(len(p) == pages, f"mélange : {pages} pages ({len(p)})")
        check(len(p) == pages and [p[i].Contents.read_raw_bytes() for i in (0, 1, -1)]
              == [a.pages[0].Contents.read_raw_bytes(), a.pages[1].Contents.read_raw_bytes(), b.pages[0].Contents.read_raw_bytes()],
              "mélange : pages PDF recopiées à l'octet près, dans l'ordre des clics")
        im, x, rot = page_image(p[2])
        check(x.read_raw_bytes() == open(f"{D}/photo.jpg", "rb").read() and rot == 90,
              "JPEG : recopié à l'octet près, redressé par la page")
        check(icc(x) == srgb, "JPEG : profil de couleurs gardé")
        check(same(page_image(p[3])[0], pattern(alpha=True)), "capture d'écran : chaque point identique, transparence comprise")
        if len(p) == pages:
            sizes = [a4_wide(p[i]) for i in range(2, 3 + has_heic + 1)]
            check(all(ok for ok, _ in sizes), f"pages photo : largeur A4 dans leur sens (portrait 21 cm, paysage 29,7 cm), proportions gardées ({[t for _, t in sizes]})")
        if has_heic and len(p) == pages:
            im, x, _ = page_image(p[4])
            check(upright(im), f"HEIC : la photo couchée est à l'endroit, couleurs justes ({im.size[0]}x{im.size[1]})")
            got = desc(icc(x)) if icc(x) else "aucun profil"
            check(got == desc(p3), f"HEIC : profil de couleurs de l'iPhone (Display P3) gardé ({got.strip()})")
            check(x.get("/Filter") == "/DCTDecode", f"HEIC : rangée en JPEG ({x.get('/Filter')})")
            n, heic_n = len(x.read_raw_bytes()), os.path.getsize(PHOTO)
            check(n < 1.2 * heic_n, f"HEIC : à peu près le poids du HEIC ({n / 1e6:.2f} Mo pour {heic_n / 1e6:.2f} Mo)")
        want_c, want_m = ts("2019-05-12T14:03:22+02:00"), ts("2018-07-04T12:00:00+00:00")
        st = os.stat(out[0])
        check(int(getattr(st, "st_birthtime", -1)) == want_c, "date de création = prise de vue la plus ancienne (12/05/2019)")
        check(int(st.st_mtime) == want_m, "date de modification = date interne du PDF la plus ancienne (04/07/2018)")
        info = {k: str(pdf.docinfo.get(k)) for k in ("/CreationDate", "/ModDate")}
        loc = lambda t: datetime.fromtimestamp(t).astimezone().strftime("D:%Y%m%d%H%M%S")
        check(info["/CreationDate"].startswith(loc(want_c)) and info["/ModDate"].startswith(loc(want_m)),
              f"dates internes du PDF identiques ({info})")
check(all((sha(f), os.stat(f).st_mtime) == hashes[f] for f in mix), "originaux intacts (contenu et dates)")

# --- 2. Images from the web and scans --------------------------------------------------------
pal = up.convert("P", palette=Image.Palette.ADAPTIVE, colors=4)
pal.save(f"{D}/logo.png", transparency=0)
pal.save(f"{D}/anim.gif", save_all=True, append_images=[up.transpose(Image.Transpose.FLIP_LEFT_RIGHT).convert("P")], transparency=0)
up.save(f"{D}/web.webp", lossless=True)
bw = up.convert("1")
up.save(f"{D}/scan.tif", save_all=True, append_images=[bw], compression="tiff_lzw")
bw.save(f"{D}/fax.tif", compression="group4", dpi=(204, 98))  # a fax: dots twice as tall as wide
turned.save(f"{D}/turned.tif", exif=ex)
ex2 = Image.Exif()
ex2[274] = 2
up.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(f"{D}/selfie.jpg", quality=95, exif=ex2)
web = ["logo.png", "anim.gif", "web.webp", "scan.tif", "fax.tif", "turned.tif", "selfie.jpg"]
out, dialogs, _ = run(*[f"{D}/{n}" for n in web])
check(len(out) == 1 and dialogs == "", f"web et scans : PDF créé sans alerte ({said(dialogs)})")
if out:
    with pikepdf.open(out[0]) as pdf:
        p = pdf.pages
        check(len(p) == 8, f"web et scans : 8 pages, GIF animé = 1 page, scan de 2 pages = 2 ({len(p)})")
        if len(p) == 8:
            want = [Image.open(f"{D}/logo.png"), Image.open(f"{D}/anim.gif"), up, up, bw, bw, up,
                    ImageOps.exif_transpose(Image.open(f"{D}/selfie.jpg"))]
            labels = ["logo PNG transparent", "GIF (1re image)", "WebP", "scan TIFF page 1", "scan TIFF page 2 (noir et blanc)",
                      "TIFF fax", "TIFF couché, redressé une seule fois", "selfie en miroir, remis à l'endroit"]
            for i, (w, lab) in enumerate(zip(want, labels)):
                check(same(page_image(p[i])[0], w), f"{lab} : chaque point identique")
            sizes = [a4_wide(pg, 204 / 98 if i == 5 else 1.0) for i, pg in enumerate(p)]
            check(all(ok for ok, _ in sizes), f"web et scans : largeur A4 dans leur sens partout ({[t for _, t in sizes]})")

# --- 3. More than 8 bits per color -------------------------------------------------------------
def png16(path, ctype):
    n = 3 if ctype == 2 else 4
    rows = b"".join(b"\0" + b"".join(struct.pack(">" + "H" * n, *[(x * 3001 + y * 77 + c * 999) % 65536 for c in range(n)])
                                       for x in range(30)) for y in range(20))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 30, 20, 16, ctype, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return zlib.compress(rows)
idat16 = png16(f"{D}/deep.png", 2)
out, dialogs, _ = run(f"{D}/deep.png")
ok = False
if out:
    with pikepdf.open(out[0]) as pdf:
        x = first_image(pdf.pages[0])
        ok = x.BitsPerComponent == 16 and x.read_raw_bytes() == idat16
check(ok and dialogs == "", f"PNG 16 bits : gardé en 16 bits, données recopiées telles quelles ({said(dialogs)})")
png16(f"{D}/deep-alpha.png", 6)
out, dialogs, _ = run(f"{D}/deep-alpha.png")
check(not out and "8 bits" in dialogs and "Aucun PDF" in dialogs, f"PNG 16 bits transparent : refusé avec un message, rien créé ({said(dialogs)})")

# --- 4. Refusals: nothing is created, the message names the file -------------------------------
open(f"{D}/notes.txt", "w").write("pas une image")
out, dialogs, _ = run(f"{D}/a.pdf", f"{D}/notes.txt")
check(not out and "notes.txt" in dialogs and "Aucun PDF" in dialogs, f"fichier non lisible au milieu : rien créé, fichier nommé ({said(dialogs)})")
pikepdf.open(f"{D}/a.pdf").save(f"{D}/locked.pdf", encryption=pikepdf.Encryption(user="secret", owner="secret"))
out, dialogs, _ = run(f"{D}/locked.pdf")
check(not out and "mot de passe" in dialogs, f"PDF protégé par mot de passe : refusé ({said(dialogs)})")
os.mkdir(f"{D}/dossier")
out, dialogs, _ = run(f"{D}/dossier")
check(not out and "dossier" in dialogs, f"dossier sélectionné : refusé ({said(dialogs)})")
os.mkdir(f"{D}/ro")
up.save(f"{D}/ro/photo.png")
os.chmod(f"{D}/ro", 0o555)
out, dialogs, _ = run(f"{D}/ro/photo.png")
check(os.listdir(f"{D}/ro") == ["photo.png"] and "Impossible d'écrire" in dialogs, f"dossier protégé en écriture : refusé, rien créé ({said(dialogs)})")

# --- 5. Alerts: the PDF is created, the message says to keep the original ----------------------
pdf = pikepdf.new()
pdf.add_blank_page()
pdf.attachments["facture.xml"] = pikepdf.AttachedFileSpec(pdf, b"<xml/>")
pdf.Root.OCProperties = pikepdf.Dictionary(OCGs=pikepdf.Array(), D=pikepdf.Dictionary())
sig = pdf.make_indirect(pikepdf.Dictionary(FT=pikepdf.Name.Sig, T="Signature1", V=pikepdf.Dictionary(Type=pikepdf.Name.Sig)))
pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array([sig]), SigFlags=3)
pdf.save(f"{D}/signe.pdf")
out, dialogs, _ = run(f"{D}/signe.pdf")
check(len(out) == 1 and all(w in dialogs for w in ("pièces jointes", "calques", "signature", "garde l'original")),
      f"pièce jointe, calques, signature : PDF créé avec l'alerte ({said(dialogs)})")

pdf = pikepdf.new()
pdf.add_blank_page()
pdf.Root.StructTreeRoot = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.StructTreeRoot))
pdf.Root.Lang = "fr-FR"
with pdf.open_outline() as outline:
    outline.root.append(pikepdf.OutlineItem("Chapitre 1", 0))
with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
    meta["dc:title"] = "Contrat"
pdf.docinfo["/Title"], pdf.docinfo["/Author"] = "Contrat", "Michael"  # after XMP, which rewrites them
pdf.Root.Names = pikepdf.Dictionary(Dests=pikepdf.Dictionary(Names=pikepdf.Array(["chap2", pikepdf.Array([pdf.pages[0].obj, pikepdf.Name.Fit])])))
pdf.save(f"{D}/balise.pdf")
out, dialogs, _ = run(f"{D}/balise.pdf")
check(len(out) == 1 and all(w in dialogs for w in ("signets", "titre", "auteur", "XMP", "accessibilité", "langue", "liens internes")),
      f"signets, titre, auteur, XMP, balisage, langue, liens internes nommés : PDF créé avec l'alerte ({said(dialogs)})")

make_pdf(f"{D}/abime.pdf", ["X1"])
raw = open(f"{D}/abime.pdf", "rb").read()
open(f"{D}/abime.pdf", "wb").write(raw[:raw.rindex(b"startxref")] + b"startxref\n999\n%%EOF\n")  # broken index
out, dialogs, _ = run(f"{D}/abime.pdf")
check(len(out) == 1 and "« abime.pdf » était abîmé" in dialogs, f"PDF abîmé : réparé, PDF créé, fichier nommé ({said(dialogs)})")


def empty_slot(path, used=False):
    """macOS writes index slots at offset 0. Unused: harmless. Used (here the page content): a
    real loss. Like macOS, the page size sits on the page tree: qpdf 12 then reads every slot."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 100))
    pdf.pages[0].Contents = pdf.make_stream(b"0 0 m 150 80 l S\n")
    pdf.Root.Pages.MediaBox = pdf.pages[0].obj.MediaBox
    del pdf.pages[0].obj.MediaBox
    pdf.save(path)
    raw = open(path, "rb").read()
    m = re.search(rb"\nxref\n0 (\d+)\n", raw)
    n, t = int(m[1]), raw.index(b"trailer", m.end())
    if used:
        k = int(re.search(rb"/Contents (\d+) 0 R", raw)[1])
        at = m.end() + 20 * k
        raw = raw[:at] + b"0000000000 00000 n \n" + raw[at + 20:]
    else:
        raw = (raw[:m.start()] + b"\nxref\n0 %d\n" % (n + 1) + raw[m.end():t] + b"0000000000 00000 n \n"
               + raw[t:].replace(b"/Size %d" % n, b"/Size %d" % (n + 1), 1))
    open(path, "wb").write(raw)


empty_slot(f"{D}/apple.pdf")
out, dialogs, _ = run(f"{D}/apple.pdf")
check(len(out) == 1 and "abîmé" not in dialogs, f"PDF de macOS à case vide inutilisée : pas d'alerte ({said(dialogs)})")
empty_slot(f"{D}/vide.pdf", used=True)
out, dialogs, _ = run(f"{D}/vide.pdf")
check(len(out) == 1 and "« vide.pdf » était abîmé" in dialogs, f"case vide utilisée : alerte ({said(dialogs)})")

# --- 6. Naming when the name is taken -----------------------------------------------------------
open(f"{D}/b 2.pdf", "w").close()
out, dialogs, _ = run(f"{D}/b.pdf")
check([os.path.basename(o) for o in out] == ["b 3.pdf"], f"nom déjà pris : « b 3.pdf » ({[os.path.basename(o) for o in out]} {said(dialogs)})")

# --- 7. Speed on a full-size iPhone photo -------------------------------------------------------
big = Image.effect_noise((4032, 3024), 40).convert("RGB")
big.save(f"{D}/big.jpg", quality=90)
out = []
if heic(f"{D}/big.jpg", f"{D}/big.heic"):
    out, dialogs, took = run(f"{D}/big.heic")
    check(len(out) == 1 and dialogs == "", f"photo HEIC de 12 Mpx : PDF créé ({said(dialogs)})")
if out:
    print(f"INFO   photo HEIC de 12 Mpx : {took:.1f} s, {os.path.getsize(f'{D}/big.heic') / 1e6:.1f} Mo en HEIC, "
          f"{os.path.getsize(out[0]) / 1e6:.1f} Mo dans le PDF")
print(f"Bilan : {oks} OK, {kos} ÉCHEC")
PY
