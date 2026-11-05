"""Créer un PDF: F1 to F10 and sections 3 to 5 of the SPEC, on the action's real script."""
import json, os, re, shutil, signal, struct, subprocess, sys, threading, time, zlib
from PIL import Image, ImageChops, ImageOps, ImageStat
import logging
import img2pdf, pikepdf
import common as C
from common import check, short

PY = sys.executable
logging.disable(logging.WARNING)  # img2pdf's notes, when the test calls it as the action does
runs = []          # every Result, for the one-alert and originals checks
touched = []       # originals changed by an action
leftovers = []     # work folders left in the action's TMPDIR


class Bench:
    def __init__(self):
        self.base = C.scratch("creer-")
        self.tmp = os.path.join(self.base, "tmpdir")
        os.mkdir(self.tmp)
        self.c = C.Creer(self.base, extra_env={"TMPDIR": self.tmp})
        self.n = 0
        # sips stand-in that logs each call, then runs the bench's sips
        self.sips_log = os.path.join(self.base, "sips.log")
        C.write_exec(os.path.join(self.c.bin, "sips"),
                     f'#!/bin/bash\necho "$@" >> "{self.sips_log}"\nexec /usr/bin/sips "$@"\n')

    def variant(self, name, mapping):
        """A copy of the action where only the given absolute paths point to stand-ins."""
        d = os.path.join(self.base, name)
        os.makedirs(d, exist_ok=True)
        return C.Creer(d, mapping=mapping, extra_env={"TMPDIR": self.tmp})

    def folder(self, name=None):
        self.n += 1
        d = os.path.join(self.base, name or f"d{self.n}")
        os.makedirs(d, exist_ok=True)
        return d

    def run(self, *files, runner=None, **kw):
        stamps = {f: (C.sha(f), os.stat(f).st_mtime) for f in files if os.path.isfile(f) and os.access(f, os.R_OK)}
        r = (runner or self.c).run(*files, **kw)
        for f, s in stamps.items():
            if os.path.exists(f) and (C.sha(f), os.stat(f).st_mtime) != s:
                touched.append(os.path.basename(f))
        if os.listdir(self.tmp):
            leftovers.append(os.listdir(self.tmp))
            for n in os.listdir(self.tmp):
                shutil.rmtree(os.path.join(self.tmp, n), ignore_errors=True)
        runs.append(r)
        return r


def pdf_pages(path):
    return pikepdf.open(path)


def raw_contents(page):
    c = page.obj.Contents
    return c.read_raw_bytes() if isinstance(c, pikepdf.Stream) else b"".join(s.read_raw_bytes() for s in c)


def streams_from(page):
    """Raw bytes of every stream reachable from a page (contents and resources, recursively)."""
    out, seen = [], set()

    def walk(o):
        if isinstance(o, pikepdf.Stream):
            key = o.objgen
            if key in seen and key != (0, 0):
                return
            seen.add(key)
            out.append(o.read_raw_bytes())
            walk(o.stream_dict)
        elif isinstance(o, pikepdf.Dictionary):
            for k, v in o.items():
                if k != "/Parent":
                    walk(v)
        elif isinstance(o, pikepdf.Array):
            for v in o:
                walk(v)
    walk(page.obj.get("/Contents"))
    walk(page.obj.get("/Resources"))
    return out


def png16(path, ctype, w=30, h=20):
    n = {0: 1, 2: 3, 6: 4}[ctype]
    rows = b"".join(b"\0" + b"".join(struct.pack(">" + "H" * n, *[(x * 3001 + y * 77 + c * 999) % 65536 for c in range(n)])
                                     for x in range(w)) for y in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    data = zlib.compress(rows)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 16, ctype, 0, 0, 0))
                + chunk(b"IDAT", data) + chunk(b"IEND", b""))
    return data


def tiff16_rgb(path, w=30, h=20):
    """A baseline uncompressed TIFF with 16 bits per sample, written by hand."""
    pix = b"".join(struct.pack("<HHH", (x * 2000) % 65536, (y * 3000) % 65536, 12345) for y in range(h) for x in range(w))
    entries = [(256, 3, 1, w), (257, 3, 1, h), (258, 3, 3, None), (259, 3, 1, 1), (262, 3, 1, 2),
               (273, 4, 1, None), (277, 3, 1, 3), (278, 3, 1, h), (279, 4, 1, len(pix))]
    ifd_off = 8
    ifd_size = 2 + 12 * len(entries) + 4
    bps_off = ifd_off + ifd_size
    data_off = bps_off + 6
    out = bytearray(b"II*\x00" + struct.pack("<I", ifd_off))
    out += struct.pack("<H", len(entries))
    for tag, typ, cnt, val in entries:
        if tag == 258:
            out += struct.pack("<HHII", tag, typ, cnt, bps_off)
        elif tag == 273:
            out += struct.pack("<HHII", tag, typ, cnt, data_off)
        elif typ == 3:
            out += struct.pack("<HHIHH", tag, typ, cnt, val, 0)
        else:
            out += struct.pack("<HHII", tag, typ, cnt, val)
    out += struct.pack("<I", 0) + struct.pack("<HHH", 16, 16, 16) + pix
    open(path, "wb").write(out)


def sampling(jpeg):
    """(component id, sampling byte) of a JPEG's frame header."""
    i = 2
    while i < len(jpeg):
        marker, size = jpeg[i + 1], int.from_bytes(jpeg[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2):
            n = jpeg[i + 9]
            return [(jpeg[i + 10 + 3 * k], jpeg[i + 11 + 3 * k]) for k in range(n)]
        i += 2 + size
    return []


def psnr(a, b):
    mse = sum(v * v for v in ImageStat.Stat(ImageChops.difference(a, b)).rms) / len(a.getbands())
    return 99 if not mse else 10 * __import__("math").log10(255 ** 2 / mse)


def display_inches(path, frame=0):
    """Displayed width and height in inches: dots over density, density turning with the image."""
    im = Image.open(path)
    im.seek(frame)
    w, h = im.size
    if hasattr(im, "tag_v2"):  # Pillow reports a turned TIFF's size already turned: use the stored one
        w, h = im.tag_v2.get(256), im.tag_v2.get(257)
    dpi = im.info.get("dpi") or (1, 1)
    if not dpi[0] or not dpi[1]:
        dpi = (1, 1)
    turn = im.tag_v2.get(274, 1) if hasattr(im, "tag_v2") else im.getexif().get(274, 1)
    iw, ih = w / dpi[0], h / dpi[1]
    return (ih, iw) if turn in (5, 6, 7, 8) else (iw, ih)


TABLE = {1: None, 2: Image.Transpose.FLIP_LEFT_RIGHT, 3: Image.Transpose.ROTATE_180, 4: Image.Transpose.FLIP_TOP_BOTTOM,
         5: Image.Transpose.TRANSPOSE, 6: Image.Transpose.ROTATE_270, 7: Image.Transpose.TRANSVERSE, 8: Image.Transpose.ROTATE_90}


def oracle(im, o):
    return im.transpose(TABLE[o]) if TABLE[o] is not None else im


def empty_slot(path, used=False, ref=None, objstm=False):
    """macOS writes index slots at offset 0. Unused: harmless. Used (here the page content): a
    real loss. Like macOS, the page size sits on the page tree, so qpdf 12 reads every slot.
    ref rewrites the page's reference to its content with the same length (odd spacing)."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 100))
    pdf.pages[0].Contents = pdf.make_stream(b"0 0 m 150 80 l S\n")
    pdf.Root.Pages.MediaBox = pdf.pages[0].obj.MediaBox
    del pdf.pages[0].obj.MediaBox
    if objstm:
        pdf.save(path, object_stream_mode=pikepdf.ObjectStreamMode.generate, compress_streams=False,
                 stream_decode_level=pikepdf.StreamDecodeLevel.none)
        return xref_stream_empty(path)
    pdf.save(path)
    raw = open(path, "rb").read()
    m = re.search(rb"\nxref\n0 (\d+)\n", raw)
    n, t = int(m[1]), raw.index(b"trailer", m.end())
    k = int(re.search(rb"/Contents (\d+) 0 R", raw)[1])
    if used:
        at = m.end() + 20 * k
        raw = raw[:at] + b"0000000000 00000 n \n" + raw[at + 20:]
        if ref:
            old = b"/Contents %d 0 R /" % k
            new = ref(k)
            assert len(new) == len(old) and raw.count(old) == 1
            raw = raw.replace(old, new)
    else:
        raw = (raw[:m.start()] + b"\nxref\n0 %d\n" % (n + 1) + raw[m.end():t] + b"0000000000 00000 n \n"
               + raw[t:].replace(b"/Size %d" % n, b"/Size %d" % (n + 1), 1))
    open(path, "wb").write(raw)


def xref_stream_empty(path):
    """Turn the xref-stream entry of the page content into an empty slot (type 1, offset 0):
    the only reference to it is then inside an object stream."""
    raw = open(path, "rb").read()
    with pikepdf.open(path) as pdf:
        k = pdf.pages[0].obj.Contents.objgen[0]
    m = list(re.finditer(rb"(\d+) 0 obj\s*<<([^>]*?/Type\s*/XRef.*?)>>\s*stream\r?\n", raw, re.S))[-1]
    head = m.group(2)
    w = [int(v) for v in re.search(rb"/W\s*\[\s*(\d+)\s+(\d+)\s+(\d+)\s*\]", head).groups()]
    length = int(re.search(rb"/Length (\d+)", head)[1])
    start = m.end()
    data = raw[start:start + length]
    if b"/FlateDecode" in head:
        data = zlib.decompress(data)
    pred = re.search(rb"/Predictor (\d+)", head)
    row = sum(w)
    if pred and int(pred[1]) >= 10:
        rows, prev, out = [], bytearray(row), bytearray()
        for i in range(0, len(data), row + 1):
            ft, line = data[i], bytearray(data[i + 1:i + 1 + row])
            if ft == 2:
                for j in range(row):
                    line[j] = (line[j] + prev[j]) & 0xFF
            out += line
            prev = line
        data = bytes(out)
    first = 0
    idx = re.search(rb"/Index\s*\[\s*(\d+)\s+(\d+)", head)
    if idx:
        first = int(idx[1])
    entries = [bytearray(data[i:i + row]) for i in range(0, len(data), row)]
    e = entries[k - first]
    e[:] = bytes([1]) + bytes(w[1]) + bytes(w[2]) if w[0] == 1 else e
    data = b"".join(entries)
    head2 = re.sub(rb"/Filter\s*/FlateDecode", b"", head)
    head2 = re.sub(rb"/DecodeParms\s*<<[^>]*>>", b"", head2)
    head2 = re.sub(rb"/Length \d+", b"/Length %d" % len(data), head2)
    obj = m.group(1) + b" 0 obj\n<<" + head2 + b">>\nstream\n" + data + b"\nendstream\nendobj\n"
    off = m.start()
    tail = raw[start + length:]
    tail = tail[tail.index(b"endobj") + len(b"endobj"):]
    new = raw[:off] + obj + b"startxref\n%d\n%%%%EOF\n" % off
    open(path, "wb").write(new)


def main():
    b = Bench()
    srgb, p3 = C.srgb_profile(), C.p3_profile()
    up = C.pattern()
    turned = up.transpose(Image.Transpose.ROTATE_90)
    jan24 = C.ts("2024-01-01T10:00:00")

    # --- F1 ------------------------------------------------------------------------------
    d = b.folder()
    C.make_pdf(f"{d}/a.pdf", ["A1", "A2"])
    C.make_pdf(f"{d}/b.pdf", ["B1"])
    turned.save(f"{d}/photo.jpg", quality=92, exif=C.exif(6), icc_profile=srgb)
    capture = C.pattern(mode="RGBA")
    capture.save(f"{d}/capture.png")
    for f in os.listdir(d):
        C.setdates(f"{d}/{f}", jan24)
    photo_up = ImageOps.exif_transpose(Image.open(f"{d}/photo.jpg")).convert("RGB")
    with pdf_pages(f"{d}/a.pdf") as a, pdf_pages(f"{d}/b.pdf") as bb:
        A = [raw_contents(p) for p in a.pages]
        B = raw_contents(bb.pages[0])
    r = b.run(f"{d}/a.pdf", f"{d}/photo.jpg", f"{d}/capture.png", f"{d}/b.pdf")
    ok = r.names == ["a 2.pdf"]
    if ok:
        with pdf_pages(r.new[0]) as pdf:
            p = pdf.pages
            ok = (len(p) == 5 and [raw_contents(p[i]) for i in (0, 1, 4)] == [A[0], A[1], B]
                  and C.same(C.page_image(p[2])[0], photo_up) and C.same(C.page_image(p[3])[0], capture))
    check(ok, "F1 mélange : un seul « a 2.pdf », 5 pages dans l'ordre des clics", r.names)
    check(r.quiet(), "F1 mélange : sans alerte", short(r.text))
    os.remove(r.new[0]) if r.new else None
    r = b.run(f"{d}/b.pdf", f"{d}/capture.png", f"{d}/photo.jpg", f"{d}/a.pdf")
    ok = r.names == ["b 2.pdf"]
    if ok:
        with pdf_pages(r.new[0]) as pdf:
            p = pdf.pages
            ok = (len(p) == 5 and raw_contents(p[0]) == B and C.same(C.page_image(p[1])[0], capture)
                  and C.same(C.page_image(p[2])[0], photo_up) and [raw_contents(p[3]), raw_contents(p[4])] == A)
    check(ok, "F1 ordre inverse : « b 2.pdf », pages b, capture, photo, a", r.names)
    os.remove(r.new[0]) if r.new else None
    d2 = b.folder()
    up.save(f"{d2}/vue.png")
    r = b.run(f"{d2}/vue.png")
    check(r.names == ["vue.pdf"], "F1 première image sans PDF homonyme : « vue.pdf »", r.names)
    open(f"{d}/b 2.pdf", "w").close()
    r = b.run(f"{d}/b.pdf")
    check(r.names == ["b 3.pdf"], "F1 nom pris : « b 3.pdf »", r.names)
    for n in r.new:
        os.remove(n)
    os.remove(f"{d}/b 2.pdf")
    d1, dd2 = b.folder("x1"), b.folder("x2")
    C.make_pdf(f"{d1}/a.pdf")
    C.make_pdf(f"{dd2}/b.pdf")
    before2 = os.listdir(dd2)
    r = b.run(f"{d1}/a.pdf", f"{dd2}/b.pdf")
    check(r.names == ["a 2.pdf"] and os.listdir(dd2) == before2, "F1 plusieurs dossiers : résultat dans le dossier du premier fichier", r.names)
    ro = b.folder("ro")
    up.save(f"{ro}/c.png")
    os.chmod(ro, 0o555)
    r = b.run(f"{ro}/c.png", f"{dd2}/b.pdf")
    check(not r.new and sorted(os.listdir(ro)) == ["c.png"] and os.listdir(dd2) == before2 and "Impossible d'écrire" in r.text,
          "F1 premier dossier protégé : refus « Impossible d'écrire », rien créé nulle part", short(r.text))
    check(ro in r.text and r.text.rstrip().endswith("Aucun PDF créé."), "F7 dossier en lecture seule : le message nomme le dossier", short(r.text))
    os.chmod(ro, 0o755)

    # --- F2 ------------------------------------------------------------------------------
    d = b.folder()
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 100))
    img = bytes((x * 7 + y * 3) % 256 for y in range(10) for x in range(60))
    xo = pikepdf.Stream(pdf, C.lzw(img))
    xo.Type, xo.Subtype, xo.Width, xo.Height = pikepdf.Name.XObject, pikepdf.Name.Image, 20, 10
    xo.ColorSpace, xo.BitsPerComponent, xo.Filter = pikepdf.Name.DeviceRGB, 8, pikepdf.Name.LZWDecode
    form = pikepdf.Stream(pdf, C.flate_level1(b"0 0 m 10 10 l S\n" * 40))
    form.Type, form.Subtype, form.BBox, form.Filter = pikepdf.Name.XObject, pikepdf.Name.Form, [0, 0, 20, 20], pikepdf.Name.FlateDecode
    content = pikepdf.Stream(pdf, C.flate_level1(b"q 100 0 0 50 0 0 cm /Im0 Do Q /Fm0 Do\n" + b"0 0 m 150 80 l S\n" * 50))
    content.Filter = pikepdf.Name.FlateDecode
    pdf.pages[0].Contents = content
    pdf.pages[0].Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=xo, Fm0=form))
    pdf.save(f"{d}/flux.pdf", compress_streams=False, stream_decode_level=pikepdf.StreamDecodeLevel.none)
    with pdf_pages(f"{d}/flux.pdf") as s:
        want = streams_from(s.pages[0])
    r = b.run(f"{d}/flux.pdf")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            got = streams_from(o.pages[0])
            ok = sorted(got) == sorted(want) and len(want) == 3
    check(ok, "F2 flux Flate niveau 1 et image LZW recopiés à l'octet", f"{len(want)} flux")
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 100))
    pdf.add_blank_page(page_size=(842, 1191))
    pdf.add_blank_page(page_size=(300, 400))
    pdf.pages[2].obj.Rotate = 90
    pdf.pages[2].obj.CropBox = [10, 20, 250, 380]
    pdf.save(f"{d}/boites.pdf")

    def boxes(pg):
        return ([float(v) for v in pg.mediabox], [float(v) for v in pg.obj.get("/CropBox", pg.mediabox)],
                int(pg.obj.get("/Rotate", 0)))
    with pdf_pages(f"{d}/boites.pdf") as s:
        want = [boxes(p) for p in s.pages]
    r = b.run(f"{d}/boites.pdf")
    got = []
    if r.new:
        with pdf_pages(r.new[0]) as o:
            got = [boxes(p) for p in o.pages]
    check(got == want, "F2 MediaBox, CropBox et /Rotate des pages PDF gardés", got)

    # --- F3 ------------------------------------------------------------------------------
    d = b.folder()
    up.save(f"{d}/mpo.mpo", "MPO", save_all=True, append_images=[up.transpose(Image.Transpose.FLIP_LEFT_RIGHT)])
    os.rename(f"{d}/mpo.mpo", f"{d}/stereo.jpg")
    src = open(f"{d}/stereo.jpg", "rb").read()
    r = b.run(f"{d}/stereo.jpg")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            x = C.page_image(o.pages[0])[1]
            raw = x.read_raw_bytes()
            ok = x.get("/Filter") == "/DCTDecode" and src.startswith(raw) and len(raw) < len(src) and raw.endswith(b"\xff\xd9")
    check(ok and r.quiet(), "F3 JPEG à deux images : la première seule, à l'octet, sans alerte", short(r.text))
    up.save(f"{d}/full.jpg", quality=95)
    full = open(f"{d}/full.jpg", "rb").read()
    open(f"{d}/coupe.jpg", "wb").write(full[:int(len(full) * 0.6)])
    r = b.run(f"{d}/coupe.jpg")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            ok = C.page_image(o.pages[0])[1].read_raw_bytes() == full[:int(len(full) * 0.6)]
    check(ok and r.quiet(), "F3 JPEG tronqué : recopié tel quel, sans alerte", short(r.text))
    turned.save(f"{d}/couche.jpg", quality=92, exif=C.exif(6), icc_profile=srgb)
    r = b.run(f"{d}/couche.jpg")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            im, x, rot = C.page_image(o.pages[0])
            ok = x.read_raw_bytes() == open(f"{d}/couche.jpg", "rb").read() and rot == 90 and C.icc_of(x) == srgb
    check(ok, "F3 JPEG couché : à l'octet, /Rotate 90, profil gardé")
    rgba = C.pattern(mode="RGBA")
    rgba.save(f"{d}/rgba.png")
    r = b.run(f"{d}/rgba.png")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            ok = C.same(C.page_image(o.pages[0])[0], rgba)
    check(ok, "F3 PNG transparent : chaque point identique, transparence comprise")
    for name, save in (("p3.png", lambda p: rgba.save(p, icc_profile=p3)),
                       ("p3.tif", lambda p: up.save(p, icc_profile=p3)),
                       ("p3.webp", lambda p: up.save(p, lossless=True, icc_profile=p3))):
        save(f"{d}/{name}")
        r = b.run(f"{d}/{name}")
        ok = False
        if r.new:
            with pdf_pages(r.new[0]) as o:
                ok = C.icc_of(C.page_image(o.pages[0])[1]) == p3
        check(ok, f"F3 {name} : profil Display P3 gardé à l'octet")
    w = b.folder()
    pal = up.convert("P", palette=Image.Palette.ADAPTIVE, colors=4)
    pal.save(f"{w}/logo.png", transparency=0)
    pal.save(f"{w}/anim.gif", save_all=True, append_images=[up.transpose(Image.Transpose.FLIP_LEFT_RIGHT).convert("P")], transparency=0)
    up.save(f"{w}/web.webp", lossless=True)
    bw = up.convert("1")
    up.save(f"{w}/scan.tif", save_all=True, append_images=[bw], compression="tiff_lzw")
    bw.save(f"{w}/fax.tif", compression="group4", dpi=(204, 98))
    turned.save(f"{w}/turned.tif", exif=C.exif(6))
    up.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(f"{w}/selfie.jpg", quality=95, exif=C.exif(2))
    web = ["logo.png", "anim.gif", "web.webp", "scan.tif", "fax.tif", "turned.tif", "selfie.jpg"]
    r = b.run(*[f"{w}/{n}" for n in web])
    want = [Image.open(f"{w}/logo.png"), Image.open(f"{w}/anim.gif"), up, up, bw, bw, up,
            ImageOps.exif_transpose(Image.open(f"{w}/selfie.jpg"))]
    sizes_ok = []
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            p = o.pages
            ok = len(p) == 8 and all(C.same(C.page_image(p[i])[0], want[i]) for i in range(8))
            srcs = [("logo.png", 0), ("anim.gif", 0), ("web.webp", 0), ("scan.tif", 0), ("scan.tif", 1), ("fax.tif", 0),
                    ("turned.tif", 0), ("selfie.jpg", 0)]
            if len(p) == 8:
                sizes_ok = [C.a4_rule(p[i], *display_inches(f"{w}/{n}", fr)) for i, (n, fr) in enumerate(srcs)]
    check(ok, "F3 sept images du web et scans : 8 pages, chaque point identique")
    check(r.quiet(), "F3 sept images : sans alerte", short(r.text))
    check(sizes_ok and all(s for s, _ in sizes_ok), "F5 pages des images du web et scans : largeur A4 dans leur sens", [t for _, t in sizes_ok])
    up.save(f"{w}/deux.tiff", save_all=True, append_images=[bw])
    up.save(f"{w}/image.bmp")
    r = b.run(f"{w}/deux.tiff", f"{w}/image.bmp")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            p = o.pages
            ok = (len(p) == 3 and C.same(C.page_image(p[0])[0], up) and C.same(C.page_image(p[1])[0], bw)
                  and C.same(C.page_image(p[2])[0], up) and not any(C.page_image(q)[1].get("/Filter") == "/DCTDecode" for q in p))
    check(ok and r.quiet(), "F3 .tiff de 2 pages et .bmp : points identiques, aucun JPEG, sans alerte", short(r.text))
    for ctype, lab in ((2, "RGB"), (0, "gris")):
        data = png16(f"{w}/deep{ctype}.png", ctype)
        r = b.run(f"{w}/deep{ctype}.png")
        ok = False
        if r.new:
            with pdf_pages(r.new[0]) as o:
                x = C.page_xobject(o.pages[0])
                ok = x.BitsPerComponent == 16 and x.read_raw_bytes() == data
        check(ok and r.quiet(), f"F3 PNG 16 bits {lab} : 16 bits, données IDAT recopiées, sans alerte", short(r.text))
    open(b.sips_log, "w").close()
    up.save(f"{w}/x.dng", "TIFF")
    C.heic(f"{w}/y.tif", up)
    up.save(f"{w}/z.tif", "PNG")
    for name, via in (("x.dng", True), ("y.tif", True), ("z.tif", False)):
        open(b.sips_log, "w").close()
        r = b.run(f"{w}/{name}")
        called = name in open(b.sips_log).read()
        ok = False
        if r.new:
            with pdf_pages(r.new[0]) as o:
                im, x, _ = C.page_image(o.pages[0])
                ok = (x.get("/Filter") == "/DCTDecode") if via else C.same(im, up)
        check(called == via and ok, f"F3 {name} : {'passé à sips, JPEG' if via else 'pas passé à sips, points gardés'}",
              f"sips={called}")

    # --- F4 ------------------------------------------------------------------------------
    h = b.folder()
    photo = Image.effect_noise((600, 400), 30).convert("RGB")
    photo = Image.blend(photo, C.pattern(600, 400), 0.7)
    C.heic(f"{h}/photo.heic", photo, icc_profile=p3, quality=90)
    r = b.run(f"{h}/photo.heic")
    ok = False
    stream1 = None
    if r.new:
        with pdf_pages(r.new[0]) as o:
            x = C.page_image(o.pages[0])[1]
            stream1 = x.read_raw_bytes()
            subprocess.run(["/usr/bin/sips", "-s", "format", "png", f"{h}/photo.heic", "--out", f"{h}/dec.png"], capture_output=True)
            dec = ImageOps.exif_transpose(Image.open(f"{h}/dec.png"))
            dec.save(f"{h}/dec.ppm", "PPM")
            open(f"{h}/p.icc", "wb").write(dec.info.get("icc_profile", b""))
            subprocess.run(["/opt/homebrew/opt/mozjpeg/bin/cjpeg", "-quality", "88", "-sample", "2x2", "-outfile", f"{h}/ref.jpg",
                            "-icc", f"{h}/p.icc", f"{h}/dec.ppm"], check=True)
            ok = (x.get("/Filter") == "/DCTDecode" and sampling(stream1) == [(1, 0x22), (2, 0x11), (3, 0x11)]
                  and stream1 == open(f"{h}/ref.jpg", "rb").read() and C.icc_of(x) == p3)
    check(ok, "F4 HEIC : JPEG mozjpeg qualité 88, 4:2:0, octets égaux à cjpeg, profil gardé")
    check(r.quiet(), "F4 HEIC : sans alerte", short(r.text))
    for n in r.new:
        os.remove(n)
    r = b.run(f"{h}/photo.heic")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            ok = C.page_image(o.pages[0])[1].read_raw_bytes() == stream1
    check(ok, "F4 HEIC : deux lancements, flux identiques à l'octet")
    alpha = C.pattern(120, 80, "RGBA")
    C.heic(f"{h}/alpha.heic", alpha)
    r = b.run(f"{h}/alpha.heic")
    ok = False
    if r.new:
        subprocess.run(["/usr/bin/sips", "-s", "format", "png", f"{h}/alpha.heic", "--out", f"{h}/alpha.png"], capture_output=True)
        with pdf_pages(r.new[0]) as o:
            im, x, _ = C.page_image(o.pages[0])
            ok = x.get("/Filter") != "/DCTDecode" and C.same(im, Image.open(f"{h}/alpha.png"))
    check(ok, "F4 HEIC transparent : PNG sans perte, points identiques au décodage")
    opaque = C.pattern(120, 80, "RGBA")
    opaque.putalpha(255)
    C.heic(f"{h}/opaque.heic", opaque)
    r = b.run(f"{h}/opaque.heic")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            ok = C.page_image(o.pages[0])[1].get("/Filter") == "/DCTDecode"
    check(ok, "F4 HEIC à alpha opaque : rangé en JPEG")
    fake = os.path.join(b.base, "cjpeg-db")
    C.write_exec(fake, f'''#!{PY}
import math, os, sys, random
from PIL import Image, ImageChops, ImageStat
a = sys.argv[1:]
out, src = a[a.index("-outfile") + 1], a[-1]
target = float(os.environ["CJPEG_DB"])
im = Image.open(src).convert("RGB")
def measure(b):
    mse = sum(v * v for v in ImageStat.Stat(ImageChops.difference(im, b)).rms) / 3
    return 10 * math.log10(255 ** 2 / mse)
lo, hi = 0.0, 128.0
for _ in range(40):
    s = (lo + hi) / 2
    noise = Image.effect_noise(im.size, s).convert("RGB")
    cand = ImageChops.add(im, noise, 1, -128)
    cand.save(out, "JPEG", quality=100)
    got = measure(Image.open(out))
    if abs(got - target) < 0.15:
        break
    if got > target:
        lo = s
    else:
        hi = s
''')
    runner = b.variant("db", {"/opt/homebrew/opt/mozjpeg/bin/cjpeg": fake})
    for db, refused in ((19, True), (21, False)):
        r = b.run(f"{h}/photo.heic", runner=runner, env={"CJPEG_DB": str(db)})
        if refused:
            check(not r.new and "photo.heic" in r.text and "ne peut pas être converti fidèlement" in r.text,
                  "F4 seuil : 19 dB refusé, fichier nommé", short(r.text))
        else:
            check(len(r.new) == 1, "F4 seuil : 21 dB accepté", short(r.text))
        for n in r.new:
            os.remove(n)
    Image.blend(Image.effect_noise((300, 200), 30).convert("RGB"), C.pattern(300, 200), 0.6).save(f"{h}/photo.avif")
    open(b.sips_log, "w").close()
    r = b.run(f"{h}/photo.avif")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            ok = C.page_image(o.pages[0])[1].get("/Filter") == "/DCTDecode"
    check(ok and "photo.avif" in open(b.sips_log).read() and r.quiet(), "F4 AVIF : passé à sips, JPEG, sans alerte", short(r.text))
    C.heic(f"{h}/big.heic", Image.effect_noise((4032, 3024), 40).convert("RGB"), quality=90)
    r = b.run(f"{h}/big.heic")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            ok = len(o.pages) == 1
    check(ok and r.quiet(), "F4 HEIC de bruit 12 Mpx : une page, sans alerte", short(r.text))
    open(f"{h}/notes.txt", "w").write("pas une image")
    r = b.run(f"{h}/notes.txt")
    check(not r.new and "notes.txt" in r.text and r.text.rstrip().endswith("Aucun PDF créé."), "F4 fichier qu'aucun décodeur ne lit : refusé, nommé", short(r.text))

    # --- F5 ------------------------------------------------------------------------------
    s = b.folder()
    C.pattern(400, 600).save(f"{s}/portrait.png")
    C.pattern(500, 500).save(f"{s}/carre.png")
    C.pattern(600, 400).save(f"{s}/dots.png", dpi=(204, 98))
    C.pattern(60, 40).convert("1").save(f"{s}/faxcouche.tif", compression="group4", dpi=(204, 98), exif=C.exif(6))
    C.pattern(60, 40).save(f"{s}/rgbcouche.tif", dpi=(204, 98), exif=C.exif(6))
    C.pattern(60, 40).save(f"{s}/miroir.jpg", quality=95, dpi=(200, 100), exif=C.exif(2))
    C.pattern(60, 40).save(f"{s}/transpose.jpg", quality=95, dpi=(200, 100), exif=C.exif(5))
    names = ["portrait.png", "carre.png", "dots.png", "faxcouche.tif", "rgbcouche.tif", "miroir.jpg", "transpose.jpg"]
    r = b.run(*[f"{s}/{n}" for n in names])
    res = []
    if r.new:
        with pdf_pages(r.new[0]) as o:
            res = [C.a4_rule(o.pages[i], *display_inches(f"{s}/{n}")) for i, n in enumerate(names)] if len(o.pages) == 7 else []
    check(res and all(x for x, _ in res), "F5 portrait, carré, points non carrés, fax et TIFF couchés, JPEG EXIF 2 et 5 : largeur A4, proportions affichées",
          [t for _, t in res])
    if res:
        check(res[2][1] == "21.00 x 29.14 cm" and res[3][1] in ("29.70 x 21.40 cm", "29.70 x 21.39 cm", "29.70 x 21.41 cm"),
              "F5 exemples chiffrés : PNG 600 x 400 à 204 x 98 dpi 21,0 x 29,14 cm, fax couché 29,7 x 21,40 cm", [res[2][1], res[3][1]])
    for fmt in ("jpg", "tif", "png"):
        m = b.folder()
        files = []
        for o in range(1, 9):
            p = f"{m}/o{o}.{fmt}"
            if fmt == "jpg":
                up.save(p, quality=95, dpi=(204, 98), exif=C.exif(o))
            elif fmt == "tif":
                up.save(p, dpi=(204, 98), exif=C.exif(o))
            else:
                up.save(p, dpi=(204, 98), exif=C.exif(o))
            files.append(p)
        r = b.run(*files)
        bad = []
        if r.new:
            with pdf_pages(r.new[0]) as pdf:
                for o in range(1, 9):
                    pg = pdf.pages[o - 1]
                    good, txt = C.a4_rule(pg, *display_inches(files[o - 1]))
                    src = Image.open(files[o - 1]).convert("RGB") if fmt == "jpg" else up
                    if not good or not C.same(C.page_image(pg)[0], oracle(src, o)):
                        bad.append(f"{o}:{txt}")
        else:
            bad = ["aucun PDF : " + short(r.text, 100)]
        check(not bad, f"F5 matrice {fmt.upper()} orientations 1 à 8 : taille et points", bad)
    z = b.folder()
    up.save(f"{z}/zero.jpg", quality=95)
    raw = bytearray(open(f"{z}/zero.jpg", "rb").read())
    j = raw.index(b"JFIF\0") + 7
    raw[j:j + 5] = b"\x01\x00\x48\x00\x00"  # units dpi, 72 x 0
    open(f"{z}/zero.jpg", "wb").write(raw)
    up.save(f"{z}/zero.png", dpi=(72, 0))
    up.save(f"{z}/rien.png", dpi=(0, 0))
    for n in ("zero.jpg", "zero.png"):
        r = b.run(f"{z}/{n}")
        check(not r.new and n in r.text and r.text.rstrip().endswith("Aucun PDF créé."), f"F5 densité nulle sur un axe ({n}) : refusé, nommé", short(r.text))
    r = b.run(f"{z}/rien.png")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            w_, h_ = C.page_cm(o.pages[0])
            ok = abs(w_ - 29.7) < 0.01 and abs(h_ - 19.8) < 0.05
    check(ok, "F5 densité 0 x 0 : 29,7 x 19,8 cm")
    C.pattern(1200, 800).save(f"{z}/fin.png", dpi=(300, 300))
    C.pattern(60, 40).save(f"{z}/gros.png", dpi=(72, 72))
    r = b.run(f"{z}/fin.png", f"{z}/gros.png")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            ok = all(abs(C.page_cm(pg)[0] - 29.7) < 0.01 and abs(C.page_cm(pg)[1] - 19.8) < 0.05 for pg in o.pages)
    check(ok, "F5 résolutions mêlées : les deux pages à 29,7 x 19,8 cm")

    # --- F6 ------------------------------------------------------------------------------
    g = b.folder()
    png16(f"{g}/deep-alpha.png", 6)
    r = b.run(f"{g}/deep-alpha.png")
    check(not r.new and "8 bits" in r.text and "Aucun PDF" in r.text, "F6 PNG 16 bits transparent : refusé", short(r.text))
    up.transpose(Image.Transpose.FLIP_LEFT_RIGHT).convert("CMYK").save(f"{g}/cmyk.jpg", quality=95, exif=C.exif(2))
    r = b.run(f"{g}/cmyk.jpg")
    check(not r.new and "cmyk.jpg" in r.text and "à l'identique" in r.text and r.text.rstrip().endswith("Aucun PDF créé."),
          "F6 JPEG CMYK miroir : refusé « à l'identique »", short(r.text))
    for mode in ("L", "RGBA", "P"):
        im = C.pattern(60, 40, "RGBA" if mode == "RGBA" else "RGB")
        im = im.convert(mode) if mode != "RGBA" else im
        im.save(f"{g}/couche-{mode}.tif", exif=C.exif(6))
        r = b.run(f"{g}/couche-{mode}.tif")
        check(not r.new and f"couche-{mode}.tif" in r.text and "TIFF mal lu par Pillow" in r.text,
              f"F6 TIFF non compressé couché en {mode} : refusé « TIFF mal lu par Pillow »", short(r.text))
    C.pattern(60, 40).save(f"{g}/couche-RGB.tif", exif=C.exif(6))
    r = b.run(f"{g}/couche-RGB.tif")
    ok = False
    if r.new:
        with pdf_pages(r.new[0]) as o:
            ok = C.same(C.page_image(o.pages[0])[0], C.pattern(60, 40).transpose(Image.Transpose.ROTATE_270))
    check(ok, "F6 TIFF non compressé couché en RGB : page identique à l'endroit")
    Image.new("I;16", (30, 20)).save(f"{g}/gris16.tif")
    tiff16_rgb(f"{g}/rgb16.tif")
    for n in ("gris16.tif", "rgb16.tif"):
        r = b.run(f"{g}/{n}")
        check(not r.new and n in r.text and "8 bits" in r.text and r.text.rstrip().endswith("Aucun PDF créé."),
              f"F6 TIFF 16 bits ({n}) : refusé d'emblée", short(r.text))
    second = {"logo.png": Image.open(f"{w}/logo.png"), "anim.gif": Image.open(f"{w}/anim.gif"), "turned.tif": up,
              "selfie.jpg": ImageOps.exif_transpose(Image.open(f"{w}/selfie.jpg"))}
    for n, want in second.items():
        first_differs = True
        try:
            k = img2pdf.convert(f"{w}/{n}", rotation=img2pdf.Rotation.ifvalid, first_frame_only=True)
            with pikepdf.open(__import__("io").BytesIO(k)) as o:
                first_differs = not C.same(C.page_image(o.pages[0])[0], want)
        except Exception:
            pass
        r = b.run(f"{w}/{n}")
        ok = False
        if r.new:
            with pdf_pages(r.new[0]) as o:
                ok = C.same(C.page_image(o.pages[0])[0], want)
        check(first_differs and ok and r.quiet(), f"F6 seconde voie ({n}) : la première voie diffère, la page finale est identique", short(r.text))
    pal.save(f"{g}/logo-p3.png", transparency=0, icc_profile=p3)
    turned.save(f"{g}/turned-p3.tif", exif=C.exif(6), icc_profile=p3)
    up.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(f"{g}/selfie-p3.jpg", quality=95, exif=C.exif(2), icc_profile=p3)
    for n in ("logo-p3.png", "turned-p3.tif", "selfie-p3.jpg"):
        r = b.run(f"{g}/{n}")
        ok = False
        if r.new:
            with pdf_pages(r.new[0]) as o:
                ok = C.icc_of(C.page_image(o.pages[0])[1]) == p3
        check(ok, f"F6 seconde voie ({n}) : profil Display P3 gardé")

    # --- F7 ------------------------------------------------------------------------------
    f7 = b.folder()
    C.make_pdf(f"{f7}/a.pdf")
    open(f"{f7}/notes.txt", "w").write("pas une image")
    r = b.run(f"{f7}/a.pdf", f"{f7}/notes.txt")
    check(not r.new and "notes.txt" in r.text and "Aucun PDF" in r.text, "F7 fichier illisible au milieu : rien créé, fichier nommé", short(r.text))
    open(f"{f7}/fake.pdf", "w").write("<html><body>404</body></html>")
    up.save(f"{f7}/x.pdf", "PNG")
    for n in ("fake.pdf", "x.pdf"):
        r = b.run(f"{f7}/{n}")
        check(not r.new and f"« {n} » n'est pas un PDF lisible." in r.text and "Aucun PDF créé." in r.text, f"F7 {n} : « n'est pas un PDF lisible »", short(r.text))
    for fmt in ("png", "gif", "tif", "bmp", "webp"):
        p = f"{f7}/coupe.{fmt}"
        (up.convert("P") if fmt == "gif" else up).save(p, **({"lossless": True} if fmt == "webp" else {}))
        data = open(p, "rb").read()
        open(p, "wb").write(data[:int(len(data) * 0.6)])
        listing = sorted(os.listdir(f7))
        r = b.run(p)
        words = ("à l'identique",) if fmt != "webp" else ("à l'identique", "n'est pas une image lisible")
        check(not r.new and f"coupe.{fmt}" in r.text and any(x in r.text for x in words) and r.text.rstrip().endswith("Aucun PDF créé.")
              and sorted(os.listdir(f7)) == listing, f"F7 {fmt.upper()} tronqué : refusé, nommé, dossier inchangé", short(r.text))
    up.save(f"{f7}/secret.png")
    os.chmod(f"{f7}/secret.png", 0)
    r = b.run(f"{f7}/secret.png")
    check(not r.new and "secret.png" in r.text and "n'a pas pu être lu" in r.text and r.text.rstrip().endswith("Aucun PDF créé."),
          "F7 image sans droit de lecture : « n'a pas pu être lu »", short(r.text))
    os.chmod(f"{f7}/secret.png", 0o644)
    disk_full(b, up)
    qpdf_doubles(b)
    pikepdf.open(f"{f7}/a.pdf").save(f"{f7}/locked.pdf", encryption=pikepdf.Encryption(user="secret", owner="secret"))
    r = b.run(f"{f7}/locked.pdf")
    check(not r.new and "locked.pdf" in r.text and "mot de passe" in r.text and "Aucun PDF créé." in r.text, "F7 PDF protégé par mot de passe : refusé, nommé", short(r.text))
    os.mkdir(f"{f7}/Classeur 7")
    r = b.run(f"{f7}/Classeur 7", folder=f7)
    check(not r.new and "Classeur 7" in r.text and "dossier" in r.text and "Aucun PDF créé." in r.text, "F7 dossier sélectionné : refusé, nommé", short(r.text))

    # --- F8 ------------------------------------------------------------------------------
    f8 = b.folder()
    C.make_pdf(f"{f8}/p1.pdf")
    C.make_pdf(f"{f8}/p2.pdf")
    r = b.run(f"{f8}/p1.pdf", f"{f8}/p2.pdf")
    check(r.quiet(), "F8 deux PDF propres : sans alerte", short(r.text))
    pdf = pikepdf.new()
    pdf.add_blank_page()
    pdf.Root.PageLayout, pdf.Root.PageMode = pikepdf.Name.TwoColumnLeft, pikepdf.Name.UseThumbs
    pdf.Root.ViewerPreferences = pikepdf.Dictionary(HideToolbar=True)
    pdf.save(f"{f8}/prefs.pdf")
    r = b.run(f"{f8}/prefs.pdf")
    check(r.quiet(), "F8 PageLayout, PageMode, ViewerPreferences : sans alerte", short(r.text))
    pdf = pikepdf.new()
    pdf.add_blank_page()
    pdf.attachments["facture.xml"] = pikepdf.AttachedFileSpec(pdf, b"<xml/>")
    pdf.Root.OCProperties = pikepdf.Dictionary(OCGs=pikepdf.Array(), D=pikepdf.Dictionary())
    sig = pdf.make_indirect(pikepdf.Dictionary(FT=pikepdf.Name.Sig, T="Signature1", V=pikepdf.Dictionary(Type=pikepdf.Name.Sig)))
    pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array([sig]), SigFlags=3)
    pdf.save(f"{f8}/signe.pdf")
    r = b.run(f"{f8}/signe.pdf")
    check(len(r.new) == 1 and all(x in r.text for x in ("pièces jointes", "calques", "signature")) and r.text.count("garde l'original") == 3,
          "F8 pièce jointe, calques, signature : « garde l'original » trois fois", short(r.text))
    pdf = pikepdf.new()
    pdf.add_blank_page()
    sig = pdf.make_indirect(pikepdf.Dictionary(FT=pikepdf.Name.Sig, T="Signature1"))
    pdf.Root.AcroForm = pikepdf.Dictionary(Fields=pikepdf.Array([sig]))
    pdf.save(f"{f8}/sigvide.pdf")
    r = b.run(f"{f8}/sigvide.pdf")
    check(len(r.new) == 1 and "signature" not in r.text, "F8 champ de signature vide : pas d'alerte signature", short(r.text))
    pdf = pikepdf.new()
    pdf.add_blank_page()
    pdf.Root.StructTreeRoot = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.StructTreeRoot))
    pdf.Root.Lang = "fr-FR"
    with pdf.open_outline() as outline:
        outline.root.append(pikepdf.OutlineItem("Chapitre 1", 0))
    with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
        meta["dc:title"] = "Contrat"
    pdf.docinfo["/Title"], pdf.docinfo["/Author"], pdf.docinfo["/Subject"] = "Contrat", "Michael", "Bail"
    pdf.Root.Names = pikepdf.Dictionary(Dests=pikepdf.Dictionary(Names=pikepdf.Array(["c2", pikepdf.Array([pdf.pages[0].obj, pikepdf.Name.Fit])])))
    pdf.save(f"{f8}/balise.pdf")
    r = b.run(f"{f8}/balise.pdf")
    check(len(r.new) == 1 and all(x in r.text for x in ("signets", "titre", "auteur", "sujet ou mots-clés", "XMP", "accessibilité", "langue", "liens internes")),
          "F8 éléments de document perdus : une ligne chacun", short(r.text))
    for name, setup, word in (("dests.pdf", lambda p: setattr(p.Root, "Dests", pikepdf.Dictionary(c2=pikepdf.Array([p.pages[0].obj, pikepdf.Name.Fit]))), "liens internes"),
                              ("keywords.pdf", lambda p: p.docinfo.__setitem__("/Keywords", "loyer"), "sujet ou mots-clés"),
                              ("subject.pdf", lambda p: p.docinfo.__setitem__("/Subject", "loyer"), "sujet ou mots-clés")):
        pdf = pikepdf.new()
        pdf.add_blank_page()
        setup(pdf)
        pdf.save(f"{f8}/{name}")
        r = b.run(f"{f8}/{name}")
        check(len(r.new) == 1 and word in r.text, f"F8 {name} seul : « {word} »", short(r.text))
    titled = []
    for n in range(5):
        titled.append(C.make_pdf(f"{f8}/titre{n}.pdf", [f"T{n}"], {"/Title": f"Titre {n}"}))
    pdf = pikepdf.new()
    pdf.add_blank_page()
    pdf.Root.OCProperties = pikepdf.Dictionary(OCGs=pikepdf.Array(), D=pikepdf.Dictionary())
    pdf.save(f"{f8}/calque.pdf")
    r = b.run(*titled[:3], f"{f8}/calque.pdf", *titled[3:])
    lines = r.lines()
    at = lambda word: next((i for i, l in enumerate(lines) if word in l), -1)
    tl = [l for l in lines if l.startswith("titre non repris")]
    check(len(r.new) == 1 and -1 < at("calques") < at("titre non repris") and len(tl) == 1
          and all(f"titre{k}.pdf" in tl[0] for k in range(3)) and "et 2 autres" in tl[0],
          "F8 beaucoup de PDF : grave d'abord, une ligne par élément, trois noms et « et 2 autres »", short(r.text))
    C.make_pdf(f"{f8}/abime.pdf", ["X1"])
    raw = open(f"{f8}/abime.pdf", "rb").read()
    open(f"{f8}/abime.pdf", "wb").write(raw[:raw.rindex(b"startxref")] + b"startxref\n999\n%%EOF\n")
    r = b.run(f"{f8}/abime.pdf")
    check(len(r.new) == 1 and "« abime.pdf » était abîmé" in r.text, "F8 PDF abîmé : réparé, nommé", short(r.text))
    for n in r.new:
        os.remove(n)
    r = b.run(f"{f8}/calque.pdf", f"{f8}/abime.pdf", titled[0])
    lines = r.lines()
    at = lambda word: next((i for i, l in enumerate(lines) if word in l), -1)
    check(-1 < at("calques") < at("était abîmé") < at("date de création") < at("titre non repris"),
          "F8 ordre : calques, abîmé, date, titre", short(r.text))
    for n in r.new:
        os.remove(n)
    bad_exif = C.write_exec(os.path.join(b.base, "exiftool-ko"), "#!/bin/sh\necho boom >&2\nexit 1\n")
    rx = b.variant("exko", {"/opt/homebrew/bin/exiftool": bad_exif})
    r = b.run(f"{f8}/calque.pdf", f"{f8}/abime.pdf", titled[0], runner=rx)
    lines = r.lines()
    at = lambda word: next((i for i, l in enumerate(lines) if word in l), -1)
    check(-1 < at("calques") < at("illisibles") < at("était abîmé") < at("date de création") < at("titre non repris"),
          "F8 ordre avec exiftool en échec : calques, illisibles, abîmé, date, titre", short(r.text))
    for n in r.new:
        os.remove(n)
    empty_slot(f"{f8}/apple.pdf")
    r = b.run(f"{f8}/apple.pdf")
    check(len(r.new) == 1 and "abîmé" not in r.text, "F8 PDF de macOS à case vide inutilisée : pas d'alerte « abîmé »", short(r.text))
    variants = (("vide.pdf", None), ("vide-blancs.pdf", lambda k: b"/Contents %d\n0  R/" % k), ("vide-zero.pdf", lambda k: b"/Contents 0%d 0 R/" % k))
    for name, ref in variants:
        empty_slot(f"{f8}/{name}", used=True, ref=ref)
        r = b.run(f"{f8}/{name}")
        check(len(r.new) == 1 and f"« {name} » était abîmé" in r.text, f"F8 case vide utilisée ({name}) : alerte", short(r.text))
    empty_slot(f"{f8}/vide-objstm.pdf", used=True, objstm=True)
    r = b.run(f"{f8}/vide-objstm.pdf")
    check(len(r.new) == 1 and "« vide-objstm.pdf » était abîmé" in r.text, "F8 case vide visée depuis un flux d'objets : alerte", short(r.text))

    # --- F9 ------------------------------------------------------------------------------
    dates(b, up)

    # --- F10 -----------------------------------------------------------------------------
    for tool in ("qpdf", "img2pdf", "exiftool", "mozjpeg"):
        pre = os.path.join(b.base, f"prefix-{tool}")
        os.makedirs(f"{pre}/bin")
        os.makedirs(f"{pre}/opt/mozjpeg/bin")
        for t in ("qpdf", "img2pdf", "exiftool"):
            if t != tool:
                os.symlink(f"{C.PREFIX}/bin/{t}", f"{pre}/bin/{t}")
        if tool != "mozjpeg":
            os.symlink(f"{C.PREFIX}/opt/mozjpeg/bin/cjpeg", f"{pre}/opt/mozjpeg/bin/cjpeg")
        rr = b.variant(f"run-{tool}", {C.PREFIX: pre})
        r = b.run(f"{f7}/a.pdf", runner=rr)
        check(not r.new and f"{tool} est introuvable" in r.text and f"brew install {tool}" in r.text and "Aucun PDF créé." in r.text,
              f"F10 {tool} absent : dialogue, rien créé", short(r.text))

    # --- Section 5 -----------------------------------------------------------------------
    e = b.folder()
    up.save(f"{e}/é'\"\\ x.png")
    r = b.run(f"{e}/é'\"\\ x.png")
    check(r.names == ["é'\"\\ x.pdf"], "section 5 nom exotique d'image : même nom en .pdf", r.names)
    C.make_pdf(f"{e}/é'\"\\ y.pdf")
    r = b.run(f"{e}/é'\"\\ y.pdf")
    check(r.names == ["é'\"\\ y 2.pdf"], "section 5 nom exotique de PDF : « … y 2.pdf »", r.names)
    weird = C.write_exec(os.path.join(b.base, "exiftool-1"), "#!/bin/sh\necho '[1]'\n")
    rw = b.variant("ex1", {"/opt/homebrew/bin/exiftool": weird})
    r = b.run(f"{f7}/a.pdf", runner=rw)
    check(not r.new and "erreur inattendue" in r.text and "Aucun PDF créé" in r.text, "section 5 erreur inattendue avant écriture : dite, rien créé", short(r.text))
    hook = C.write_exec(os.path.join(b.base, "lock-folder"), '#!/bin/sh\nchmod 000 "$(dirname "$1")"\n')
    lk = b.folder("verrouille")
    up.save(f"{lk}/v.png")
    r = b.run(f"{lk}/v.png", env={"DATES_HOOK": hook})
    os.chmod(lk, 0o755)
    exists = os.path.exists(f"{lk}/v.pdf")
    check(exists and r.dialogs and r.dialogs[0].startswith("« v.pdf » est créé, mais à vérifier : erreur inattendue (PermissionError : ")
          and "Aucun PDF créé" not in r.text, "section 5 erreur inattendue après écriture : PDF gardé et nommé", short(r.text))
    interrupted(b)
    concurrency(b)
    fallback(b, up)

    # --- Aggregates ------------------------------------------------------------------------
    many = [r.dialogs for r in runs if len(r.calls) > 1]
    check(not many, "F8 une seule alerte par lancement", many[:2])
    check(not touched, "section 3 originaux jamais touchés (contenu et date de modification)", touched)
    check(not leftovers, "section 5 dossier de travail nettoyé après chaque lancement", leftovers[:2])


def disk_full(b, up):
    """F7: the result does not fit on a small volume mounted in a user namespace."""
    d = os.path.join(b.base, "plein")
    os.mkdir(d)
    src = os.path.join(b.base, "bruit.png")
    Image.effect_noise((120, 120), 80).convert("RGB").save(src)
    size = os.path.getsize(src)
    log = os.path.join(b.base, "plein.log")
    open(log, "w").close()
    listing = os.path.join(b.base, "plein.ls")
    kib = (size * 3 // 2) // 1024 + 4
    script = (f'mount -t tmpfs -o size={kib}k tmpfs "{d}" && cp "{src}" "{d}/bruit.png" && '
              f'bash "{b.c.script}" "{d}/bruit.png"; ls -A "{d}" > "{listing}"')
    env = b.c.env(log)
    subprocess.run(["unshare", "-rm", "bash", "-c", script], env=env, capture_output=True)
    dialogs = [json.loads(line)["argv"][-1] for line in open(log)]
    text = "\n".join(dialogs)
    left = open(listing).read().split() if os.path.exists(listing) else ["?"]
    check(left == ["bruit.png"] and "Écriture impossible" in text and "Aucun PDF créé." in text,
          "F7 écriture qui échoue au milieu (volume plein) : rien ne reste, « Écriture impossible »", f"{left} {short(text)}")


def qpdf_doubles(b):
    """F7: qpdf failing, dropping a page, or warning without naming a file."""
    fake = C.write_exec(os.path.join(b.base, "qpdf-double"), f'''#!/bin/bash
case "$QPDF_MODE" in
  fail) echo "qpdf: boom" >&2; exit 2 ;;
  drop) "{C.PREFIX}/bin/qpdf" "$@" || exit $?
        out="${{@: -1}}"; "{C.PREFIX}/bin/qpdf" "$out" --pages "$out" 1-r2 -- "$out.cut" && mv "$out.cut" "$out" ;;
  warn) "{C.PREFIX}/bin/qpdf" "$@"; echo "WARNING: something odd happened" >&2; exit 3 ;;
esac
''')
    rq = b.variant("qd", {"/opt/homebrew/bin/qpdf": fake})
    d = os.path.join(b.base, "qdocs")
    os.mkdir(d)
    C.make_pdf(f"{d}/deux.pdf", ["A", "B"])
    r = b.run(f"{d}/deux.pdf", runner=rq, env={"QPDF_MODE": "fail"})
    check(not r.new and "L'assemblage a échoué" in r.text, "F7 qpdf en échec : « L'assemblage a échoué », rien créé", short(r.text))
    r = b.run(f"{d}/deux.pdf", runner=rq, env={"QPDF_MODE": "drop"})
    check(not r.new and "Des pages se sont perdues" in r.text, "F7 page perdue à l'assemblage : refus, rien créé", short(r.text))
    r = b.run(f"{d}/deux.pdf", runner=rq, env={"QPDF_MODE": "warn"})
    check(len(r.new) == 1 and "« un PDF source » était abîmé" in r.text, "F7 avertissement qpdf sans nom de fichier : « un PDF source »", short(r.text))


def dates(b, up):
    jan24 = C.ts("2024-01-01T10:00:00")

    def one(make, name):
        d = b.folder()
        p = os.path.join(d, name)
        make(p)
        C.setdates(p, jan24)
        r = b.run(p)
        info = {}
        mtime = None
        if r.new:
            with pikepdf.open(r.new[0]) as o:
                info = {k: str(o.docinfo.get(k)) for k in ("/CreationDate", "/ModDate")}
            mtime = int(os.stat(r.new[0]).st_mtime)
        return r, info, mtime

    def jpg(taken, offset=None):
        return lambda p: up.save(p, quality=90, exif=C.exif(taken=taken, offset=offset))

    r, info, mt = one(jpg("2019:05:12 14:03:22", "+02:00"), "photo.jpg")
    check(info.get("/CreationDate") == "D:20190512140322+02'00'" and info.get("/ModDate") == "D:20240101100000+01'00'" and mt == jan24,
          "F9 prise de vue seule plus ancienne : création 2019, modification du Finder", info)
    r, info, mt = one(lambda p: C.make_pdf(p, info={"/CreationDate": "D:20200301100000+01'00'"}), "c.pdf")
    check(info.get("/CreationDate") == "D:20200301100000+01'00'", "F9 CreationDate de PDF seule plus ancienne", info)
    r, info, mt = one(lambda p: C.make_pdf(p, info={"/ModDate": "D:20180704120000Z"}), "m.pdf")
    check(info.get("/ModDate") == "D:20180704140000+02'00'" and mt == C.ts("2018-07-04T12:00:00+00:00"),
          "F9 ModDate de PDF seule plus ancienne : /ModDate et fichier", f"{info} {mt}")
    d = b.folder()
    p = C.make_pdf(os.path.join(d, "vieux.pdf"))
    old = C.ts("2017-03-02T10:00:00")
    C.setdates(p, old)
    r = b.run(p)
    info, mt = {}, None
    if r.new:
        with pikepdf.open(r.new[0]) as o:
            info = {k: str(o.docinfo.get(k)) for k in ("/CreationDate", "/ModDate")}
        mt = int(os.stat(r.new[0]).st_mtime)
    check(info.get("/ModDate") == "D:20170302100000+01'00'" and info.get("/CreationDate") == "D:20170302100000+01'00'" and mt == old,
          "F9 modification du Finder seule plus ancienne (VM : création aussi)", f"{info} {mt}")
    for cd, md, want_c, want_m, lab in (
            ("D:19800101000000Z", "D:19850101000000Z", "D:20240101100000+01'00'", "D:20240101100000+01'00'", "1980 et 1985 ignorées"),
            ("D:19921231235959Z", "D:19921231235959Z", "D:20240101100000+01'00'", "D:20240101100000+01'00'", "1992 ignorée"),
            ("D:19930101000000Z", "D:19930101000000Z", "D:19930101010000+01'00'", "D:19930101010000+01'00'", "1993 retenue")):
        r, info, mt = one(lambda p: C.make_pdf(p, info={"/CreationDate": cd, "/ModDate": md}), "borne.pdf")
        check(info.get("/CreationDate") == want_c and info.get("/ModDate") == want_m, f"F9 dates PDF : {lab}", info)
    r, info, mt = one(jpg("1899:12:31 00:00:00"), "vieille.jpg")
    check(info.get("/CreationDate") == "D:20240101100000+01'00'", "F9 prise de vue de 1899 ignorée", info)
    r, info, mt = one(jpg("1900:01:01 00:00:00"), "1900.jpg")
    check(str(info.get("/CreationDate", "")).startswith("D:19000101000000"), "F9 prise de vue de 1900 retenue", info)
    r, info, mt = one(jpg("2019:05:12 14:03:22"), "sansfuseau.jpg")
    check(info.get("/CreationDate") == "D:20190512140322+02'00'", "F9 prise de vue sans décalage : heure locale", info)
    r, info, mt = one(lambda p: C.heic(p, up, exif=C.exif(taken="2015:03:04 05:06:07", offset="+01:00").tobytes()), "date.heic")
    check(info.get("/CreationDate") == "D:20150304050607+01'00'", "F9 date de prise de vue d'un HEIC", info)
    d = b.folder()
    p = C.make_pdf(os.path.join(d, "noop.pdf"))
    C.setdates(p, jan24)
    r = b.run(p, env={"DATES_NOOP": "1"})
    check("la date de modification du fichier n'a pas pu être recalée" in r.text and "la date de création du fichier n'a pas pu être recalée" in r.text,
          "F9 dates relues : alerte si elles n'ont pas pu être recalées", short(r.text))
    bad = C.write_exec(os.path.join(b.base, "exiftool-ko2"), "#!/bin/sh\nexit 1\n")
    rx = b.variant("ex9", {"/opt/homebrew/bin/exiftool": bad})
    r = b.run(p, runner=rx)
    check(len(r.new) == 1 and "illisibles" in r.text, "F9 exiftool en échec : PDF créé, alerte « illisibles »", short(r.text))


def interrupted(b):
    """Section 5: SIGTERM, then SIGKILL, as soon as the result starts being written."""
    d = os.path.join(b.base, "gros")
    os.mkdir(d)
    pdf = pikepdf.new()
    for i in range(3):
        pdf.add_blank_page()
        pdf.pages[-1].Contents = pdf.make_stream(os.urandom(15_000_000))
    pdf.save(f"{d}/gros.pdf", compress_streams=False)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        before = set(os.listdir(d))
        p, log = b.c.run(f"{d}/gros.pdf", popen=True)
        t0 = time.time()
        while time.time() - t0 < 120 and p.poll() is None:
            if any("(PDF en cours" in n for n in os.listdir(d)):
                break
            time.sleep(0.002)
        os.killpg(p.pid, sig)
        p.wait()
        new = sorted(set(os.listdir(d)) - before)
        bad = []
        for n in new:
            if n.endswith(".pdf"):
                try:
                    with pikepdf.open(f"{d}/{n}") as o:
                        if len(o.pages) != 3:
                            bad.append(n)
                except Exception:
                    bad.append(n)
        if sig == signal.SIGTERM:
            temps = [n for n in new if "(PDF en cours" in n]
            work = os.listdir(b.tmp)
            check(not bad and not temps and not work, "section 5 arrêt par SIGTERM pendant l'écriture : aucun PDF partiel, rien ne reste",
                  f"{new} {work}")
        else:
            check(not bad, "section 5 arrêt par SIGKILL pendant l'écriture : aucun PDF partiel sous un nom de résultat", new)
        for n in new:
            os.remove(f"{d}/{n}")
        for n in os.listdir(b.tmp):
            shutil.rmtree(os.path.join(b.tmp, n), ignore_errors=True)
    # Polling: no *.pdf seen empty or smaller than its final size
    p, log = b.c.run(f"{d}/gros.pdf", popen=True)
    seen = {}
    while p.poll() is None:
        for n in os.listdir(d):
            if n.endswith(".pdf") and n != "gros.pdf":
                try:
                    seen.setdefault(n, set()).add(os.path.getsize(f"{d}/{n}"))
                except OSError:
                    pass
    p.wait()
    final = {n: os.path.getsize(f"{d}/{n}") for n in os.listdir(d) if n.endswith(".pdf") and n != "gros.pdf"}
    check(seen and all(sizes == {final.get(n)} for n, sizes in seen.items()),
          "section 4 sondage : un résultat n'apparaît jamais vide ni incomplet", {n: sorted(s) for n, s in seen.items()})


def concurrency(b):
    """Section 4: 8 launches started together, 10 rounds."""
    bad = []
    for rnd in range(10):
        d = os.path.join(b.base, f"course{rnd}")
        os.mkdir(d)
        C.make_pdf(f"{d}/b.pdf")
        gate = os.path.join(d, ".go")
        log = os.path.join(b.base, f"course{rnd}.log")
        open(log, "w").close()
        env = b.c.env(log)
        procs = [subprocess.Popen(["bash", "-c", f'while [ ! -e "{gate}" ]; do :; done; exec bash "{b.c.script}" "{d}/b.pdf"'], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(8)]
        time.sleep(0.3)
        open(gate, "w").close()
        for p in procs:
            p.wait()
        os.remove(gate)
        names = sorted(n for n in os.listdir(d) if n != "b.pdf")
        want = sorted(f"b {k}.pdf" for k in range(2, 10))
        valid = True
        for n in names:
            try:
                with pikepdf.open(f"{d}/{n}") as o:
                    valid &= len(o.pages) == 1
            except Exception:
                valid = False
        if names != want or not valid:
            bad.append((rnd, names))
    check(not bad, "section 4 huit lancements simultanés, dix tours : huit noms distincts, PDF valides, aucun provisoire", bad[:2])


def fallback(b, up):
    """Section 4: without hard links, the final name is claimed directly and the PDF is whole."""
    run_dir = os.path.join(b.base, "nolink")
    os.makedirs(run_dir)
    c = C.Creer(run_dir, extra_env={"TMPDIR": b.tmp})
    script = open(c.script).read()
    assert script.count("os.link(temp, target)") == 1
    script = script.replace("os.link(temp, target)", "(_ for _ in ()).throw(OSError(1, 'no hard links'))")
    open(c.script, "w").write(script)
    d = os.path.join(b.base, "nolinkdocs")
    os.mkdir(d)
    C.make_pdf(f"{d}/a.pdf", ["A", "B"])
    r = b.run(f"{d}/a.pdf", runner=c)
    ok = r.names == ["a 2.pdf"]
    if ok:
        with pikepdf.open(r.new[0]) as o:
            ok = len(o.pages) == 2
    check(ok, "section 4 repli sans lien dur : PDF complet sous son nom, aucun provisoire", r.names)
