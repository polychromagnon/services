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
"$PY" -I - "$T" <<'PY'
import hashlib, io, os, struct, subprocess, sys, time, zlib
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
    subprocess.run(["/bin/bash", os.path.join(T, "action.sh"), *files], capture_output=True,
                   env={"PATH": f"{T}/bin:/usr/bin:/bin:/usr/sbin:/sbin", "DIALOG_LOG": log, "HOME": os.environ["HOME"]})
    new = sorted(set(os.listdir(folder)) - before)
    return [os.path.join(folder, n) for n in new], open(log).read(), time.time() - t0


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


def same(a, b):
    mode = "RGBA" if "A" in a.mode + b.mode or "transparency" in b.info else "RGB"
    return a.size == b.size and a.convert(mode).tobytes() == b.convert(mode).tobytes()


def near(a, b):
    """Lossy formats (HEIC): same size and each quarter of about the same color."""
    if a.size != b.size:
        return False
    a, b = a.convert("RGB").resize((2, 2), Image.Resampling.BOX), b.convert("RGB").resize((2, 2), Image.Resampling.BOX)
    return all(abs(p - q) < 40 for p, q in zip(a.tobytes(), b.tobytes()))


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
turned.save(f"{D}/p3.jpg", quality=95, exif=ex, icc_profile=p3)
subprocess.run(["sips", "-s", "format", "heic", f"{D}/p3.jpg", "--out", f"{D}/iphone.heic"], capture_output=True)
mix = [f"{D}/a.pdf", f"{D}/photo.jpg", f"{D}/capture.png", f"{D}/iphone.heic", f"{D}/b.pdf"]
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
        check(len(p) == 6, f"mélange : 6 pages ({len(p)})")
        check(len(p) == 6 and [p[i].Contents.read_raw_bytes() for i in (0, 1, 5)]
              == [a.pages[0].Contents.read_raw_bytes(), a.pages[1].Contents.read_raw_bytes(), b.pages[0].Contents.read_raw_bytes()],
              "mélange : pages PDF recopiées à l'octet près, dans l'ordre des clics")
        im, x, rot = page_image(p[2])
        check(x.read_raw_bytes() == open(f"{D}/photo.jpg", "rb").read() and rot == 90,
              "JPEG : recopié à l'octet près, redressé par la page")
        check(x.ColorSpace[0] == "/ICCBased" and x.ColorSpace[1].read_bytes() == srgb, "JPEG : profil de couleurs gardé")
        check(same(page_image(p[3])[0], pattern(alpha=True)), "capture d'écran : chaque point identique, transparence comprise")
        if os.path.exists(f"{D}/iphone.heic"):
            im, x, _ = page_image(p[4])
            check(near(im, up), "HEIC : page à l'endroit, couleurs justes")
            check(x.ColorSpace[0] == "/ICCBased" and desc(x.ColorSpace[1].read_bytes()) == desc(p3),
                  "HEIC : profil de couleurs de l'iPhone (Display P3) gardé")
        else:
            check(False, "HEIC : sips n'a pas pu fabriquer la photo d'essai")
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
bw.save(f"{D}/fax.tif", compression="group4")
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
check(not out and "8 bits" in dialogs and "Aucun PDF" in dialogs, "PNG 16 bits transparent : refusé avec un message, rien créé")

# --- 4. Refusals: nothing is created, the message names the file -------------------------------
open(f"{D}/notes.txt", "w").write("pas une image")
out, dialogs, _ = run(f"{D}/a.pdf", f"{D}/notes.txt")
check(not out and "notes.txt" in dialogs and "Aucun PDF" in dialogs, "fichier non lisible au milieu : rien créé, fichier nommé")
pikepdf.open(f"{D}/a.pdf").save(f"{D}/locked.pdf", encryption=pikepdf.Encryption(user="secret", owner="secret"))
out, dialogs, _ = run(f"{D}/locked.pdf")
check(not out and "mot de passe" in dialogs, "PDF protégé par mot de passe : refusé")
os.mkdir(f"{D}/dossier")
out, dialogs, _ = run(f"{D}/dossier")
check(not out and "dossier" in dialogs, "dossier sélectionné : refusé")
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
      "pièce jointe, calques, signature : PDF créé avec l'alerte")

# --- 6. Naming when the name is taken -----------------------------------------------------------
open(f"{D}/b 2.pdf", "w").close()
out, _, _ = run(f"{D}/b.pdf")
check([os.path.basename(o) for o in out] == ["b 3.pdf"], "nom déjà pris : « b 3.pdf »")

# --- 7. Speed on a full-size iPhone photo -------------------------------------------------------
big = Image.effect_noise((4032, 3024), 40).convert("RGB")
big.save(f"{D}/big.jpg", quality=90)
subprocess.run(["sips", "-s", "format", "heic", f"{D}/big.jpg", "--out", f"{D}/big.heic"], capture_output=True)
out, dialogs, took = run(f"{D}/big.heic")
check(len(out) == 1 and dialogs == "", f"photo HEIC de 12 Mpx : PDF créé ({said(dialogs)})")
if out:
    print(f"INFO   photo HEIC de 12 Mpx : {took:.1f} s, {os.path.getsize(f'{D}/big.heic') / 1e6:.1f} Mo en HEIC, "
          f"{os.path.getsize(out[0]) / 1e6:.1f} Mo dans le PDF")
print(f"Bilan : {oks} OK, {kos} ÉCHEC")
PY
