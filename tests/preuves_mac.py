"""Logic of preuves-mac.sh: the SPEC's [Mac] proofs and gestures, in the SPEC's order.
Off macOS (the VM), proofs that need the real Mac print SAUTÉ."""
import json, os, re, shutil, signal, subprocess, sys, tempfile, time

REPO = sys.argv[1]
sys.path.insert(0, os.path.join(REPO, "tests"))
import common as C  # noqa: E402
import test_rotation as TR  # noqa: E402
import pikepdf  # noqa: E402

MAC = sys.platform == "darwin"
EXPECT_ROTATE = 90
TRACE = os.environ.get("PREUVES_TRACE")
WORK = tempfile.mkdtemp(prefix="preuves-mac-")
ZSH = "/bin/zsh" if os.path.exists("/bin/zsh") else shutil.which("zsh") or "zsh"

OSASCRIPT = r'''#!/usr/bin/python3
# Dialogs and Terminal commands are logged; date calls go to the real osascript.
import json, os, subprocess, sys
a = sys.argv[1:]
script = "" if a[:2] == ["-l", "JavaScript"] or sys.stdin.isatty() else sys.stdin.read()
if a[:2] == ["-l", "JavaScript"] or "NSURLCreationDateKey" in script:
    sys.exit(subprocess.run(["/usr/bin/osascript", *a], input=script, text=True).returncode)
with open(os.environ["OSA_LOG"], "a") as f:
    f.write(json.dumps({"argv": a, "stdin": script}) + "\n")
'''


def say(status, label, detail=""):
    print(status.ljust(7) + label + (f" ({detail})" if detail and status == "ÉCHEC" else ""), flush=True)


def proof(label, fn, mac_only=True):
    if mac_only and not MAC:
        return say("SAUTÉ", label)
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__} : {e}"
    say("OK" if ok else "ÉCHEC", label, C.short(detail, 300))


def gesture(label, steps):
    say("GESTE", f"{label} : {steps}")


def trace(**kw):
    if TRACE:
        with open(TRACE, "a") as f:
            f.write(json.dumps(kw) + "\n")


def doubles():
    d = os.path.join(WORK, "bin")
    if not os.path.isdir(d):
        os.makedirs(d)
        for n, text in (("cat", TR.CAT), ("cmp", TR.CMP), ("cp", TR.CP), ("osascript", OSASCRIPT)):
            C.write_exec(os.path.join(d, n), text)
    return d


def env(extra=None):
    log = tempfile.mktemp(dir=WORK, suffix=".log")
    open(log, "w").close()
    prefix = os.environ.get("PREUVES_PATH_PREFIX", "")
    e = {"PATH": ":".join(p for p in (doubles(), prefix, "/usr/bin:/bin:/usr/sbin:/sbin") if p), "HOME": os.environ["HOME"],
         "OSA_LOG": log, "ROTATE_ANGLE": "+90", "CAT_MARK": os.path.join(WORK, "cat.mark"), "CP_MARK": os.path.join(WORK, "cp.mark"),
         "DIALOG_LOG": log}
    e.update(extra or {})
    return e, log


def logged(log):
    return [json.loads(line) for line in open(log)]


def birth(path):
    if MAC:
        return int(os.stat(path).st_birthtime)
    return int(subprocess.run(["stat", "-c", "%W", path], capture_output=True, text=True).stdout)


def rotations(path):
    with pikepdf.open(path) as pdf:
        return [int(p.obj.get("/Rotate", 0)) % 360 for p in pdf.pages]


def rotate(path, extra=None, bash="/bin/bash"):
    e, log = env(extra)
    r = subprocess.run([bash, os.path.join(REPO, "rotation-pdf.sh"), path], env=e, capture_output=True, text=True)
    text = "\n".join(c["argv"][-1] for c in logged(log))
    return r, text


def interrupt(path, sig, extra, mark):
    e, log = env(extra)
    if os.path.exists(e[mark]):
        os.remove(e[mark])
    p = subprocess.Popen(["/bin/bash", os.path.join(REPO, "rotation-pdf.sh"), path], env=e, process_group=0,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    trace(launcher=os.getpgid(0), scenario=os.getpgid(p.pid))
    t0 = time.time()
    while not os.path.exists(e[mark]) and time.time() - t0 < 30:
        time.sleep(0.01)
    os.killpg(os.getpgid(p.pid), sig)
    p.wait()


def setdates(path, created, modified):
    os.utime(path, (modified, modified))
    subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", """function run(a) { ObjC.import('Foundation');
      $.NSFileManager.defaultManager.setAttributesOfItemAtPathError($.NSDictionary.dictionaryWithObjectForKey(
      $.NSDate.dateWithTimeIntervalSince1970(Number(a[1])), 'NSFileCreationDate'), a[0], null); }""", path, str(created)],
                   capture_output=True)


state = {}


def selftest():
    if "selftest" not in state:
        photo = os.path.normpath(os.path.join(REPO, "..", "test-HEIC", "img.heic"))
        before = C.sha(photo) if os.path.exists(photo) else None
        r = subprocess.run(["/bin/bash", os.path.join(REPO, "test-creer-pdf.sh")], capture_output=True, text=True)
        state["selftest"] = (r.stdout.splitlines(), before, C.sha(photo) if os.path.exists(photo) else None)
    return state["selftest"]


def f4_photo():
    lines, _, _ = selftest()
    heic = [l for l in lines if l[7:].startswith("HEIC")] + [l for l in lines if l[7:].startswith("mélange : aucune alerte")]
    return len(heic) >= 5 and all(l.startswith("OK") for l in heic), heic


def f9_dates():
    d = os.path.join(WORK, "dates")
    os.makedirs(d)
    C.make_pdf(f"{d}/a.pdf", ["A"])
    C.make_pdf(f"{d}/b.pdf", ["B"], {"/ModDate": "D:20180704120000Z"})
    C.pattern().save(f"{d}/photo.jpg", quality=90, exif=C.exif(taken="2019:05:12 14:03:22", offset="+02:00"))
    for f in ("a.pdf", "photo.jpg", "b.pdf"):
        setdates(f"{d}/{f}", C.ts("2023-01-01T10:00:00"), C.ts("2024-01-01T10:00:00"))
    c = C.Creer(os.path.join(WORK, "creer"))
    r = c.run(f"{d}/a.pdf", f"{d}/photo.jpg", f"{d}/b.pdf")
    got = []
    if r.new:
        st = os.stat(r.new[0])
        got = [int(st.st_birthtime), int(st.st_mtime)]
        state["mod_before_creation"] = r.new[0]
    want = [C.ts("2019-05-12T14:03:22+02:00"), C.ts("2018-07-04T12:00:00+00:00")]
    ok = got == want and not r.dialogs
    C.make_pdf(f"{d}/vieux.pdf")
    setdates(f"{d}/vieux.pdf", C.ts("2015-06-01T09:00:00"), C.ts("2024-01-01T10:00:00"))
    r2 = c.run(f"{d}/vieux.pdf")
    ok2 = bool(r2.new) and int(os.stat(r2.new[0]).st_birthtime) == C.ts("2015-06-01T09:00:00")
    photo = os.path.normpath(os.path.join(REPO, "..", "test-HEIC", "img.heic"))
    ok3, info = True, "photo absente"
    if os.path.exists(photo):
        shutil.copy(photo, f"{d}/img.heic")
        rec = json.loads(subprocess.run(["/opt/homebrew/bin/exiftool", "-j", "-n", "-DateTimeOriginal", "-OffsetTimeOriginal", photo],
                                        capture_output=True, text=True).stdout)[0]
        taken = rec["DateTimeOriginal"].replace(":", "-", 2).replace(" ", "T") + rec.get("OffsetTimeOriginal", "")
        r3 = c.run(f"{d}/img.heic")
        ok3 = bool(r3.new) and int(os.stat(r3.new[0]).st_birthtime) == int(C.datetime.fromisoformat(taken).timestamp())
        info = taken
    return ok and ok2 and ok3, f"mélange {got} pour {want}, 2015 {ok2}, photo {info} {ok3}"


def f11_selftest():
    lines, before, after = selftest()
    return bool(lines) and re.match(r"^Bilan : \d+ OK, 0 ÉCHEC$", lines[-1]) is not None and before == after and before is not None, \
        f"{lines[-1] if lines else ''}, photo {'intacte' if before == after else 'modifiée'}"


def f12_dates():
    pdf = state.get("mod_before_creation")
    if not pdf:
        return False, "pas de PDF de la preuve F9"
    pdf2 = os.path.join(WORK, "rot.pdf")
    shutil.copy2(pdf, pdf2)
    setdates(pdf2, C.ts("2019-05-12T14:03:22+02:00"), C.ts("2018-07-04T12:00:00+00:00"))
    dates = lambda: (birth(pdf2), int(os.stat(pdf2).st_mtime))
    before = dates()
    rotate(pdf2)
    ok1 = dates() == before
    data = open(pdf2, "rb").read()
    r, text = rotate(pdf2, {"CMP_LIE": "1"})
    ok2 = dates() == before and open(pdf2, "rb").read() == data and "remis a l'identique" in text
    interrupt(pdf2, signal.SIGTERM, {"CAT_MODE": "slow-rotated"}, "CAT_MARK")
    ok3 = dates() == before and open(pdf2, "rb").read() == data
    return ok1 and ok2 and ok3, f"rotation {ok1}, remise {ok2}, interruption {ok3}"


def f12_bash():
    version = subprocess.run(["/bin/bash", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    d = os.path.join(WORK, "bash")
    os.makedirs(f"{d}/vide")
    res = {}
    C.make_pdf(f"{d}/ok.pdf")
    b0 = birth(f"{d}/ok.pdf")
    r, text = rotate(f"{d}/ok.pdf")
    res["succès"] = r.returncode == 0 and rotations(f"{d}/ok.pdf") == [EXPECT_ROTATE] and birth(f"{d}/ok.pdf") == b0
    e, log = env()
    r = subprocess.run(["/bin/bash", os.path.join(REPO, "rotation-pdf.sh"), f"{d}/vide"], env=e, capture_output=True, text=True)
    res["dossier vide"] = r.returncode == 0 and not r.stderr and not logged(log)
    C.make_pdf(f"{d}/m.pdf")
    data = open(f"{d}/m.pdf", "rb").read()
    r, text = rotate(f"{d}/m.pdf", {"CMP_LIE": "1"})
    res["remise"] = open(f"{d}/m.pdf", "rb").read() == data and "remis a l'identique" in text
    C.make_pdf(f"{d}/t.pdf", ["A", "B"])
    data = open(f"{d}/t.pdf", "rb").read()
    interrupt(f"{d}/t.pdf", signal.SIGTERM, {"CAT_MODE": "slow-rotated"}, "CAT_MARK")
    res["SIGTERM"] = open(f"{d}/t.pdf", "rb").read() == data and not os.path.exists(f"{d}/t.pdf.rotation-pdf-lock")
    C.make_pdf(f"{d}/c.pdf", ["A", "B"])
    data = open(f"{d}/c.pdf", "rb").read()
    interrupt(f"{d}/c.pdf", signal.SIGKILL, {"CP_MODE": "slow"}, "CP_MARK")
    r, text = rotate(f"{d}/c.pdf")
    res["cp interrompu"] = open(f"{d}/c.pdf", "rb").read() == data and "copie-de-securite.pdf" not in text
    C.make_pdf(f"{d}/v.pdf")
    os.mkdir(f"{d}/v.pdf.rotation-pdf-lock")
    data = open(f"{d}/v.pdf", "rb").read()
    r, text = rotate(f"{d}/v.pdf")
    res["verrou"] = "une autre rotation" in text and open(f"{d}/v.pdf", "rb").read() == data
    ok = all(res.values()) and (not MAC or "version 3.2" in version)
    return ok, f"{version} ; {res}"


def f12_path():
    shared = os.path.expanduser("~/Developer/scripts/services/rotation-pdf.sh")
    linked = os.path.realpath(os.path.expanduser("~/Library/Services/Rotation droite.workflow"))
    other = os.path.join(os.path.dirname(linked), "rotation-pdf.sh")
    return os.path.isfile(shared) and os.path.exists(other) and os.path.samefile(shared, other), f"{shared} / {other}"


def exotic_name():
    d = os.path.join(WORK, "noms")
    os.makedirs(d, exist_ok=True)
    f = os.path.join(d, "é'\"\\ x.pdf")
    open(f, "w").write("x")
    return f


def recorder(repo, name):
    os.makedirs(repo, exist_ok=True)
    path = os.path.join(repo, name)
    open(path, "w").write("import json, os, sys\njson.dump(sys.argv[1:], open(os.environ['ARGV_LOG'], 'w'))\n")
    return path


def replay(cmd):
    argv_log = os.path.join(WORK, "argv.json")
    if os.path.exists(argv_log):
        os.remove(argv_log)
    subprocess.run([ZSH, "-c", cmd], env={"PATH": "/usr/bin:/bin", "ARGV_LOG": argv_log, "HOME": os.environ["HOME"]}, capture_output=True)
    return json.load(open(argv_log)) if os.path.exists(argv_log) else None


def f13_name():
    f = exotic_name()
    fake = recorder(os.path.join(WORK, "metmux"), "metmux.py")
    script = C.rewritten(C.command("Éditer les métadonnées"), {"/Users/michael/Developer/metmux/metmux.py": fake})
    e, log = env()
    subprocess.run(["/bin/bash", "-c", script, "bash", f], env=e, capture_output=True)
    calls = logged(log)
    got = replay(calls[0]["argv"][1]) if calls else None
    return got == ["--mode=ask", f], got


def f14_paths():
    metmux = "/Users/michael/Developer/metmux/metmux.py"
    py = "/Users/michael/Developer/ocrswap/.venv/bin/python3"
    ocr = "/Users/michael/Developer/ocrswap/ocrswap.py"
    there = os.path.isfile(metmux) and os.path.isfile(ocr) and os.access(py, os.X_OK)
    if not there:
        return False, "un chemin de production manque"
    for c in ("/opt/homebrew/bin/python3", "/usr/local/bin/python3", shutil.which("python3"), shutil.which("python")):
        if c and os.access(c, os.X_OK):
            break
    helptext = subprocess.run([c, metmux, "--help"], capture_output=True, text=True, timeout=60)
    help_ok = "--mode" in helptext.stdout + helptext.stderr and "ask" in helptext.stdout + helptext.stderr
    try:
        r = subprocess.run([py, ocr, "/chemin/inexistant/x.pdf"], capture_output=True, text=True, timeout=30)
        ocr_ok = r.returncode != 0 and "unrecognized arguments" not in r.stdout + r.stderr
        detail = C.short(r.stdout + r.stderr, 150)
    except subprocess.TimeoutExpired:
        ocr_ok, detail = False, "ocrswap n'a pas rendu la main en 30 s"
    return help_ok and ocr_ok, f"aide metmux {help_ok}, ocrswap {detail}"


def f14_name():
    f = exotic_name()
    repo = os.path.join(WORK, "ocrswap")
    script_path = recorder(repo, "ocrswap.py")
    os.makedirs(f"{repo}/.venv/bin", exist_ok=True)
    if not os.path.exists(f"{repo}/.venv/bin/python3"):
        os.symlink(sys.executable, f"{repo}/.venv/bin/python3")
    script = C.rewritten(C.command("OCR sur PDF"), {"/Users/michael/Developer/ocrswap/.venv/bin/python3": f"{repo}/.venv/bin/python3",
                                                     "/Users/michael/Developer/ocrswap/ocrswap.py": script_path})
    e, log = env()
    subprocess.run(["/bin/bash", "-c", script, "bash", f], env=e, capture_output=True)
    cmds = [a for c in logged(log) for a in c["argv"] if "do script" in a]
    got = None
    if len(cmds) == 1:
        m = re.match(r'tell application "Terminal" to do script "(.*)"$', cmds[0], re.S)
        if m:
            got = replay(re.sub(r"\\(.)", r"\1", m.group(1)))
    return got == [f], got


def f15_services():
    lib = os.path.expanduser("~/Library/Services")
    names = os.listdir(lib)
    ocr = [n for n in names if "OCR" in n]
    meta = [n for n in names if re.search(r"métadonnées|metadonnees|metmux|metadata", n, re.I)]
    return len(ocr) == 1 and len(meta) == 1, f"OCR {ocr}, métadonnées {meta}"


def icloud():
    d = tempfile.mkdtemp(prefix="Preuve Créer un PDF ", dir=os.path.expanduser("~/Documents"))
    try:
        C.make_pdf(f"{d}/a.pdf", ["A", "B"])
        c = C.Creer(os.path.join(WORK, "creer-icloud"))
        r = c.run(f"{d}/a.pdf")
        time.sleep(5)
        names = sorted(os.listdir(d))
        ok = names == ["a 2.pdf", "a.pdf"]
        if ok:
            with pikepdf.open(f"{d}/a 2.pdf") as pdf:
                ok = len(pdf.pages) == 2
        return ok, names
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    print(f"INFO   preuves Mac, {'macOS' if MAC else sys.platform} ; dossier de travail {WORK}")
    gesture("F1 ordre des clics", "dans le Finder, clique une image, puis un PDF, puis un autre PDF (Cmd-clic, dans cet ordre), "
            "puis clic droit, Créer un PDF : les pages du PDF créé suivent l'ordre de tes clics")
    proof("F4 photo réelle de l'iPhone : JPEG à l'endroit, profil Display P3, poids du HEIC, sans alerte (self-test)", f4_photo)
    proof("F9 dates de création et de modification posées sur le fichier, la modification avant la création", f9_dates)
    proof("F11 self-test : Bilan sans ÉCHEC, photo d'essai intacte", f11_selftest)
    proof("F12 rotation d'un PDF à modification plus ancienne que sa création : dates gardées, après remise et interruption aussi", f12_dates)
    proof("F12 scénarios de rotation sous /bin/bash (3.2 sur le Mac)", f12_bash, mac_only=False)
    proof("F12 les rotations installées lancent ~/Developer/scripts/services/rotation-pdf.sh", f12_path)
    proof("F13 un nom exotique arrive tel quel à metmux", f13_name, mac_only=False)
    gesture("F13 place dans le menu", "clic droit sur un fichier dans le Finder : « Éditer les métadonnées » apparaît directement en bas "
            "du menu, pas dans le sous-menu Actions rapides")
    proof("F14 metmux et ocrswap présents, leurs options attendues existent", f14_paths)
    proof("F14 un nom exotique arrive tel quel à ocrswap", f14_name, mac_only=False)
    gesture("F15 menu rafraîchi", "demande à Claude de renommer une action dans son Info.plist, lance bash sync.sh, puis clic droit dans "
            "le Finder : le nouveau nom apparaît (demande ensuite de remettre l'ancien)")
    proof("F15 une seule action OCR et une seule action de métadonnées installées", f15_services)
    proof("section 4 dossier Documents synchronisé par iCloud : un seul PDF complet, aucun fichier provisoire", icloud)
    shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    main()
