"""Shared helpers of the VM suite: extracting the actions' real scripts, stand-ins for macOS
tools, running an action, building test files. Every check prints one OK or ÉCHEC line."""
import hashlib, json, os, plistlib, subprocess, tempfile, time, zlib
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIX = "/opt/homebrew"
BARE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
TZ = "Europe/Paris"
results = {"ok": 0, "ko": 0}


def check(cond, label, detail=""):
    print(("OK     " if cond else "ÉCHEC  ") + label + (f" ({detail})" if detail and not cond else ""), flush=True)
    results["ok" if cond else "ko"] += 1
    return bool(cond)


def short(text, n=240):
    return " ".join(str(text).split())[:n]


# --- Workflows -------------------------------------------------------------------------------

def workflow(name):
    return os.path.join(REPO, f"{name}.workflow")


def plist(name, part):
    with open(os.path.join(workflow(name), "Contents", part), "rb") as f:
        return plistlib.load(f)


def shell_actions(name):
    return [a["action"]["ActionParameters"] for a in plist(name, "document.wflow")["actions"]
            if "COMMAND_STRING" in a["action"]["ActionParameters"]]


def command(name):
    """The shell script of a workflow, as it is in document.wflow right now."""
    (ap,) = shell_actions(name)
    return ap["COMMAND_STRING"]


def rewritten(script, mapping):
    """A copy of a script where only the given absolute paths are replaced; proves it."""
    out = script
    for old, new in mapping.items():
        out = out.replace(old, new)
    back = out
    for old, new in mapping.items():
        back = back.replace(new, old)
    assert back == script, "the rewritten copy differs from the original elsewhere than on its paths"
    return out


def write_exec(path, text):
    with open(path, "w") as f:
        f.write(text)
    os.chmod(path, 0o755)
    return path


def tree(root):
    """Paths and contents of a folder tree, to prove nothing changed."""
    out = {}
    for d, dirs, files in os.walk(root):
        for n in dirs + files:
            p = os.path.join(d, n)
            rel = os.path.relpath(p, root)
            if os.path.islink(p):
                out[rel] = "->" + os.readlink(p)
            elif os.path.isfile(p):
                out[rel] = sha(p)
            else:
                out[rel] = "dir"
    return out


def changed(before, after):
    """Paths that appeared, vanished or changed between two tree() snapshots."""
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# --- Créer un PDF ------------------------------------------------------------------------------

OSASCRIPT_STAND_IN = r'''#!/usr/bin/python3
# Dialogs go to a JSON-lines log; the date-setting JavaScript goes to the bench's osascript,
# unless DATES_NOOP is set (then nothing is set), or DATES_HOOK names a script to run first.
import json, os, subprocess, sys
a = sys.argv[1:]
if a[:2] == ["-l", "JavaScript"]:
    hook = os.environ.get("DATES_HOOK")
    if hook:
        subprocess.run([hook] + a[4:])
    if os.environ.get("DATES_NOOP"):
        sys.exit(0)
    os.execv("/usr/bin/osascript", ["/usr/bin/osascript"] + a)
with open(os.environ["DIALOG_LOG"], "a") as f:
    f.write(json.dumps({"argv": a, "stdin": "" if sys.stdin.isatty() else ""}) + "\n")
'''


class Creer:
    """Runs the real Créer un PDF script, or a copy with rewritten paths, with stand-ins."""

    def __init__(self, base, mapping=None, extra_env=None):
        self.base = base
        self.bin = os.path.join(base, "bin")
        os.makedirs(self.bin, exist_ok=True)
        write_exec(os.path.join(self.bin, "osascript"), OSASCRIPT_STAND_IN)
        script = command("Créer un PDF")
        if mapping:
            script = rewritten(script, mapping)
        self.script = write_exec(os.path.join(base, "action.sh"), script)
        self.extra_env = extra_env or {}

    def env(self, log):
        e = {"PATH": f"{self.bin}:{BARE_PATH}", "DIALOG_LOG": log, "HOME": os.environ["HOME"], "TZ": TZ,
             "TMPDIR": os.environ.get("TMPDIR", "/tmp")}
        e.update(self.extra_env)
        return e

    def run(self, *files, env=None, folder=None, popen=False):
        log = tempfile.mktemp(dir=self.base, suffix=".log")
        open(log, "w").close()
        folder = folder or os.path.dirname(files[0])
        before = set(os.listdir(folder)) if os.path.isdir(folder) else set()
        e = self.env(log)
        e.update(env or {})
        cmd = ["/bin/bash", self.script, *files]
        if popen:
            return subprocess.Popen(cmd, env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True), log
        r = subprocess.run(cmd, env=e, capture_output=True, text=True)
        try:
            after = set(os.listdir(folder)) if os.path.isdir(folder) else set()
        except PermissionError:  # a test may lock the folder; it then looks for itself
            after = before
        return Result(folder, sorted(after - before), log, r)


class Result:
    def __init__(self, folder, new, log, r):
        self.new = [os.path.join(folder, n) for n in new]
        self.names = new
        self.calls = [json.loads(line) for line in open(log)] if os.path.exists(log) else []
        self.dialogs = [c["argv"][-1] for c in self.calls]
        self.text = "\n".join(self.dialogs)
        self.rc = r.returncode
        self.stderr = r.stderr

    def quiet(self):
        """'Sans alerte' in the VM: only the creation-date note, which Linux cannot set."""
        if not self.new:
            return False
        name = os.path.basename(self.new[0])
        return self.dialogs == [f"« {name} » est créé, mais à vérifier :\nla date de création du fichier n'a pas pu être recalée"]

    def lines(self):
        return self.text.splitlines()


# --- Test files -----------------------------------------------------------------------------

def pattern(w=60, h=40, mode="RGB"):
    """Four colored quarters (a turn or a mirror shows) with fine noise (any loss shows)."""
    from PIL import Image
    im = Image.new("RGBA", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            q = [(220, 30, 30), (30, 200, 30), (30, 30, 220), (230, 220, 30)][(y >= h // 2) * 2 + (x >= w // 2)]
            c = tuple((v + (x * 7 + y * 13) % 9) % 256 for v in q)
            px[x, y] = c + ((x * 5 + y * 3) % 256,)
    return im if mode == "RGBA" else im.convert(mode)


def p3_profile():
    with open("/System/Library/ColorSync/Profiles/Display P3.icc", "rb") as f:
        return f.read()


def srgb_profile():
    from PIL import ImageCms
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def exif(orientation=None, taken=None, offset=None):
    from PIL import Image
    ex = Image.Exif()
    if orientation:
        ex[274] = orientation
    if taken:
        ifd = ex.get_ifd(0x8769)
        ifd[0x9003] = taken
        if offset:
            ifd[0x9011] = offset
    return ex


def make_pdf(path, labels=("P1",), info=None, size=(200, 100)):
    import pikepdf
    pdf = pikepdf.new()
    for lab in labels:
        pdf.add_blank_page(page_size=size)
        pdf.pages[-1].Contents = pdf.make_stream(f"% {lab}\n0 0 m 150 80 l S\n".encode())
    for k, v in (info or {}).items():
        pdf.docinfo[k] = v
    pdf.save(path)
    return path


def heic(path, im, **kw):
    import pillow_heif
    pillow_heif.register_heif_opener()
    im.save(path, "HEIF", **kw)
    return path


def setdates(path, mtime):
    os.utime(path, (mtime, mtime))


def ts(text):
    """Epoch of a local Paris time or an ISO time with offset."""
    os.environ["TZ"] = TZ
    time.tzset()
    return int(datetime.fromisoformat(text).timestamp())


def page_xobject(page):
    xobjects = (page.obj.get("/Resources") or {}).get("/XObject") or {}
    return [v for _, v in xobjects.items() if v.get("/Subtype") == "/Image"][0]


def page_image(page):
    """The image of a page as displayed (its /Rotate applied), its XObject and the rotation."""
    import pikepdf
    from PIL import Image
    x = page_xobject(page)
    im = pikepdf.PdfImage(x).as_pil_image()
    if "/SMask" in x and im.mode not in ("RGBA", "LA"):
        im = im.convert("RGBA")
        im.putalpha(pikepdf.PdfImage(x.SMask).as_pil_image().convert("L"))
    rot = int(page.obj.get("/Rotate", 0)) % 360
    turn = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}
    return (im.transpose(turn[rot]) if rot else im), x, rot


def icc_of(x):
    import pikepdf
    cs = x.get("/ColorSpace")
    if isinstance(cs, pikepdf.Array) and cs[0] == "/Indexed":
        cs = cs[1]
    return cs[1].read_bytes() if isinstance(cs, pikepdf.Array) and cs[0] == "/ICCBased" else b""


def same(a, b):
    mode = "RGBA" if any(i.mode in ("RGBA", "LA", "PA") or "transparency" in i.info for i in (a, b)) else "RGB"
    return a.size == b.size and a.convert(mode).tobytes() == b.convert(mode).tobytes()


def page_cm(page):
    """Displayed width and height of a page in cm (a turned page swaps its sides)."""
    mb = [float(v) for v in page.mediabox]
    w, h = (mb[2] - mb[0]) / 72 * 2.54, (mb[3] - mb[1]) / 72 * 2.54
    if int(page.obj.get("/Rotate", 0)) % 180:
        w, h = h, w
    return w, h


def a4_rule(page, inches_w, inches_h):
    """F5: 21 cm wide for a displayed portrait or square image, 29.7 cm for a landscape one,
    as tall as the displayed proportions."""
    w, h = page_cm(page)
    want = 21.0 if inches_h >= inches_w else 29.7
    return abs(w - want) < 0.01 and abs(h - want * inches_h / inches_w) < 0.05, f"{w:.2f} x {h:.2f} cm"


def flate_level1(data):
    c = zlib.compressobj(1)
    return c.compress(data) + c.flush()


def lzw(data):
    """Minimal PDF LZWDecode encoder (EarlyChange 1), for a source that a recompression changes."""
    codes = {bytes([i]): i for i in range(256)}
    nxt, width, out, buf, nbits = 258, 9, bytearray(), 0, 0

    def emit(code):
        nonlocal buf, nbits
        buf = (buf << width) | code
        nbits += width
        while nbits >= 8:
            nbits -= 8
            out.append((buf >> nbits) & 0xFF)
        buf &= (1 << nbits) - 1

    emit(256)
    w = b""
    for c in data:
        wc = w + bytes([c])
        if wc in codes:
            w = wc
            continue
        emit(codes[w])
        codes[wc] = nxt
        nxt += 1
        if nxt >= (1 << width) and width < 12:
            width += 1
        if nxt >= 4093:
            emit(256)
            codes = {bytes([i]): i for i in range(256)}
            nxt, width = 258, 9
        w = bytes([c])
    if w:
        emit(codes[w])
    emit(257)
    if nbits:
        out.append((buf << (8 - nbits)) & 0xFF)
    return bytes(out)


def scratch(prefix):
    return tempfile.mkdtemp(prefix=prefix)
