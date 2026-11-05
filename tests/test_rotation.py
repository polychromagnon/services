"""Rotation gauche and Rotation droite: F12 of the SPEC, on rotation-pdf.sh and both workflows."""
import json, os, re, shutil, signal, subprocess, time
import pikepdf
import common as C
from common import check, short

STAT = r'''#!/bin/bash
# Stand-in for macOS stat: -L -f '%d:%i' (volume:inode) and -L -f %B (creation date); after
# STAT_SHIFT_AFTER creation-date reads, adds 1000 s to simulate a creation date that moved.
if [ "$1" = "-L" ] && [ "$2" = "-f" ]; then
  fmt=$3; shift 3; [ "$1" = "--" ] && shift
  case "$fmt" in
    '%d:%i') exec /usr/bin/stat -L -c '%d:%i' -- "$1" ;;
    '%B')
      b=$(/usr/bin/stat -L -c %W -- "$1") || exit 1
      if [ -n "${STAT_SHIFT_AFTER:-}" ]; then
        n=$(( $(cat "$STAT_COUNT" 2>/dev/null || echo 0) + 1 )); echo $n > "$STAT_COUNT"
        [ "$n" -gt "$STAT_SHIFT_AFTER" ] && b=$((b + 1000))
      fi
      echo "$b"; exit 0 ;;
  esac
fi
exec /usr/bin/stat "$@"
'''

OSASCRIPT = r'''#!/usr/bin/python3
# Logs dialogs and creation-date restores (AppleScript on stdin) as JSON lines.
import json, os, sys
script = sys.stdin.read()
kind = "date" if "NSURLCreationDateKey" in script else "dialog"
with open(os.environ["OSA_LOG"], "a") as f:
    f.write(json.dumps({"kind": kind, "argv": sys.argv[1:]}) + "\n")
'''

CAT = r'''#!/bin/bash
# CAT_MODE: slow-rotated (writes 200 bytes of version-tournee.pdf, then waits), short-rotated
# (writes 200 bytes then fails), fail-backup (fails on copie-de-securite.pdf), slow (waits 1 s).
last="${@: -1}"
case "${CAT_MODE:-}:$last" in
  slow-rotated:*version-tournee.pdf) head -c 200 "$last"; : > "$CAT_MARK"; sleep 60; exit 0 ;;
  short-rotated:*version-tournee.pdf) head -c 200 "$last"; exit 1 ;;
  fail-backup:*copie-de-securite.pdf) exit 1 ;;
  slow:*version-tournee.pdf) sleep 1 ;;
esac
exec /bin/cat "$@"
'''

CMP = r'''#!/bin/bash
# Answers "different" when the rotated version is compared to the PDF, else the real cmp.
case "$*" in
  *version-tournee.pdf*) [ -n "${CMP_LIE:-}" ] && exit 1 ;;
esac
exec /usr/bin/cmp "$@"
'''

CP = r'''#!/bin/bash
# CP_MODE slow: writes 200 bytes of the source, marks, then waits.
if [ "${CP_MODE:-}" = slow ]; then
  src="${@: -2:1}"; dst="${@: -1}"; head -c 200 "$src" > "$dst"; : > "$CP_MARK"; sleep 60; exit 0
fi
exec /bin/cp "$@"
'''

SCRIPT = os.path.join(C.REPO, "rotation-pdf.sh")


class Rot:
    def __init__(self):
        self.base = C.scratch("rotation-")
        self.bin = os.path.join(self.base, "bin")
        os.makedirs(self.bin)
        for n, text in (("stat", STAT), ("osascript", OSASCRIPT), ("cat", CAT), ("cmp", CMP), ("cp", CP)):
            C.write_exec(os.path.join(self.bin, n), text)
        self.n = 0

    def folder(self):
        self.n += 1
        d = os.path.join(self.base, f"d{self.n}")
        os.makedirs(d)
        return d

    def env(self, angle, extra=None):
        log = os.path.join(self.base, f"osa{time.time_ns()}.log")
        open(log, "w").close()
        e = {"PATH": f"{self.bin}:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.environ["HOME"], "ROTATE_ANGLE": angle,
             "OSA_LOG": log, "CAT_MARK": os.path.join(self.base, "cat.mark"), "CP_MARK": os.path.join(self.base, "cp.mark"),
             "STAT_COUNT": os.path.join(self.base, f"count{time.time_ns()}")}
        e.update(extra or {})
        return e, log

    def run(self, angle, *args, script=SCRIPT, extra=None):
        e, log = self.env(angle, extra)
        r = subprocess.run(["/bin/bash", script, *args], env=e, capture_output=True, text=True)
        return Out(r.returncode, r.stderr, log)

    def start(self, angle, *args, extra=None):
        e, log = self.env(angle, extra)
        for m in (e["CAT_MARK"], e["CP_MARK"]):
            if os.path.exists(m):
                os.remove(m)
        p = subprocess.Popen(["/bin/bash", SCRIPT, *args], env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             start_new_session=True)
        return p, e, log


class Out:
    def __init__(self, rc, stderr, log):
        self.rc, self.stderr = rc, stderr
        calls = [json.loads(line) for line in open(log)]
        self.dialogs = [c["argv"][-1] for c in calls if c["kind"] == "dialog"]
        self.dates = [c["argv"] for c in calls if c["kind"] == "date"]
        self.text = "\n".join(self.dialogs)


def rotations(path):
    with pikepdf.open(path) as pdf:
        return [int(p.obj.get("/Rotate", 0)) % 360 for p in pdf.pages]


def birth(path):
    return int(subprocess.run(["/usr/bin/stat", "-c", "%W", path], capture_output=True, text=True).stdout)


def locks(folder):
    return [n for n in os.listdir(folder) if n.endswith(".rotation-pdf-lock")]


def main():
    R = Rot()
    jan20 = C.ts("2020-01-01T10:00:00")

    d = R.folder()
    for n in ("a.pdf", "g.pdf"):
        C.make_pdf(f"{d}/{n}")
        C.setdates(f"{d}/{n}", jan20)
    st, bi = os.stat(f"{d}/a.pdf"), birth(f"{d}/a.pdf")
    o = R.run("+90", f"{d}/a.pdf")
    st2 = os.stat(f"{d}/a.pdf")
    check(rotations(f"{d}/a.pdf") == [90] and st2.st_ino == st.st_ino and birth(f"{d}/a.pdf") == bi
          and int(st2.st_mtime) == jan20 and o.rc == 0 and not o.dialogs,
          "F12 Rotation droite : /Rotate 90, même inode, mêmes dates, aucun dialogue", f"{rotations(f'{d}/a.pdf')} rc={o.rc} {o.text}")
    o = R.run("-90", f"{d}/g.pdf")
    check(rotations(f"{d}/g.pdf") == [270] and o.rc == 0 and int(os.stat(f"{d}/g.pdf").st_mtime) == jan20,
          "F12 Rotation gauche : /Rotate 270, date de modification gardée", rotations(f"{d}/g.pdf"))

    d = R.folder()
    C.make_pdf(f"{d}/x.pdf")
    C.make_pdf(f"{d}/y.pdf")
    o = R.run("+90", f"{d}/x.pdf", f"{d}/y.pdf")
    check(rotations(f"{d}/x.pdf") == [90] and rotations(f"{d}/y.pdf") == [90] and "2 reussie(s), 0 echec(s)" in o.text and o.rc == 0,
          "F12 deux PDF distincts : tous deux tournés, bilan affiché", short(o.text))

    d = R.folder()
    pdf = pikepdf.new()
    for k in range(3):
        pdf.add_blank_page()
    pdf.pages[1].obj.Rotate = 90
    pdf.save(f"{d}/trois.pdf")
    R.run("+90", f"{d}/trois.pdf")
    check(rotations(f"{d}/trois.pdf") == [90, 180, 90], "F12 trois pages dont une déjà tournée : 90, 180, 90", rotations(f"{d}/trois.pdf"))

    d = R.folder()
    os.makedirs(f"{d}/dossier/sous")
    C.make_pdf(f"{d}/dossier/x.pdf")
    C.make_pdf(f"{d}/dossier/sous/y.pdf")
    os.symlink(f"{d}/dossier/x.pdf", f"{d}/lien.pdf")
    o = R.run("+90", f"{d}/dossier", f"{d}/dossier/x.pdf", f"{d}/lien.pdf")
    check(rotations(f"{d}/dossier/x.pdf") == [90] and rotations(f"{d}/dossier/sous/y.pdf") == [0],
          "F12 dossier, fichier et lien vers lui : une seule rotation, sous-dossier ignoré",
          f"{rotations(f'{d}/dossier/x.pdf')} {rotations(f'{d}/dossier/sous/y.pdf')}")

    d = R.folder()
    C.make_pdf(f"{d}/q.pdf")
    before = C.sha(f"{d}/q.pdf")
    script = C.write_exec(os.path.join(R.base, "sans-qpdf.sh"), C.rewritten(open(SCRIPT).read(), {"/opt/homebrew/bin/qpdf": "/nonexistent/qpdf"}))
    o = R.run("+90", f"{d}/q.pdf", script=script)
    check(o.rc == 1 and "qpdf est introuvable" in o.stderr and "brew install qpdf" in o.stderr and C.sha(f"{d}/q.pdf") == before,
          "F12 qpdf absent : sortie 1, message, fichier intact", short(o.stderr))

    d = R.folder()
    os.mkdir(f"{d}/vide")
    o = R.run("+90", f"{d}/vide")
    check(o.rc == 0 and not o.dialogs and not o.stderr, "F12 dossier sans PDF : sortie 0, rien affiché", short(o.stderr))

    d = R.folder()
    C.make_pdf(f"{d}/ro.pdf")
    os.chmod(f"{d}/ro.pdf", 0o444)
    before = C.sha(f"{d}/ro.pdf")
    o = R.run("+90", f"{d}/ro.pdf")
    check(o.rc == 1 and "lecture seule" in o.text and C.sha(f"{d}/ro.pdf") == before, "F12 PDF en lecture seule : intact, sortie 1", short(o.text))
    os.makedirs(f"{d}/rodir")
    C.make_pdf(f"{d}/rodir/z.pdf")
    os.chmod(f"{d}/rodir", 0o555)
    before = C.sha(f"{d}/rodir/z.pdf")
    o = R.run("+90", f"{d}/rodir/z.pdf")
    os.chmod(f"{d}/rodir", 0o755)
    check(o.rc == 1 and "dossier qui le contient est en lecture seule" in o.text and C.sha(f"{d}/rodir/z.pdf") == before,
          "F12 PDF dans un dossier en lecture seule : intact, sortie 1", short(o.text))

    content_kept(R)

    d = R.folder()
    C.make_pdf(f"{d}/abime.pdf")
    raw = open(f"{d}/abime.pdf", "rb").read()
    open(f"{d}/abime.pdf", "wb").write(raw[:raw.rindex(b"startxref")] + b"startxref\n999\n%%EOF\n")
    before = C.sha(f"{d}/abime.pdf")
    o = R.run("+90", f"{d}/abime.pdf")
    check(o.rc == 1 and "corrompu" in o.text and C.sha(f"{d}/abime.pdf") == before, "F12 PDF à l'index cassé : « corrompu », intact", short(o.text))
    import test_creer
    test_creer.empty_slot(f"{d}/apple.pdf")
    before = C.sha(f"{d}/apple.pdf")
    o = R.run("+90", f"{d}/apple.pdf")
    check(o.rc == 1 and "apple.pdf" in o.text and C.sha(f"{d}/apple.pdf") == before, "F12 PDF de macOS à case vide : refusé, nommé, intact", short(o.text))
    open(f"{d}/faux.pdf", "w").write("pas un pdf")
    o = R.run("+90", f"{d}/faux.pdf")
    check(o.rc == 1 and "rotation echouee" in o.text and open(f"{d}/faux.pdf").read() == "pas un pdf",
          "F12 fichier .pdf qui n'est pas un PDF : « rotation echouee », intact", short(o.text))

    d = R.folder()
    C.make_pdf(f"{d}/course.pdf")
    procs = [R.start("+90", f"{d}/course.pdf", extra={"CAT_MODE": "slow"}) for _ in range(4)]
    outs = []
    for p, e, log in procs:
        p.wait()
        outs.append(Out(p.returncode, p.stderr.read().decode(), log))
    wins = [o for o in outs if o.rc == 0]
    refused = [o for o in outs if o.rc == 1 and "une autre rotation" in o.text]
    check(len(wins) == 1 and len(refused) == 3 and rotations(f"{d}/course.pdf") == [90] and not locks(d),
          "F12 quatre lancements simultanés : un seul tourne, trois refus", f"{[o.rc for o in outs]} {rotations(f'{d}/course.pdf')}")

    d = R.folder()
    C.make_pdf(f"{d}/v.pdf")
    os.mkdir(f"{d}/v.pdf.rotation-pdf-lock")
    before = C.sha(f"{d}/v.pdf")
    o = R.run("+90", f"{d}/v.pdf")
    check(C.sha(f"{d}/v.pdf") == before and "une autre rotation" in o.text and locks(d) == ["v.pdf.rotation-pdf-lock"],
          "F12 verrou déjà présent : refus, verrou gardé, fichier intact", short(o.text))
    shutil.copy(f"{d}/v.pdf", f"{d}/v.pdf.rotation-pdf-lock/copie-de-securite.pdf")
    o = R.run("+90", f"{d}/v.pdf")
    t = o.text
    check("copie-de-securite.pdf" in t and "ne s'ouvre pas normalement" in t and t.find("ne s'ouvre pas") < t.find("supprimez"),
          "F12 verrou qui garde la copie : la nomme, remise avant toute suppression", short(t))

    d = R.folder()
    C.make_pdf(f"{d}/plein.pdf")
    C.setdates(f"{d}/plein.pdf", jan20)
    before = C.sha(f"{d}/plein.pdf")
    o = R.run("+90", f"{d}/plein.pdf", extra={"CAT_MODE": "short-rotated"})
    check(C.sha(f"{d}/plein.pdf") == before and "ecriture impossible" in o.text and "remis a l'identique" in o.text and not locks(d) and o.rc == 1,
          "F12 écriture en place qui échoue : remis à l'identique, aucun verrou", short(o.text))

    d = R.folder()
    C.make_pdf(f"{d}/m.pdf")
    before = C.sha(f"{d}/m.pdf")
    o = R.run("+90", f"{d}/m.pdf", extra={"CMP_LIE": "1"})
    check(C.sha(f"{d}/m.pdf") == before and "remis a l'identique" in o.text and not locks(d),
          "F12 relecture différente : remis à l'identique, aucun verrou", short(o.text))
    o = R.run("+90", f"{d}/m.pdf", extra={"CMP_LIE": "1", "CAT_MODE": "fail-backup"})
    lk = f"{d}/m.pdf.rotation-pdf-lock"
    check(os.path.isdir(lk) and C.sha(f"{lk}/copie-de-securite.pdf") == before and os.path.exists(f"{lk}/version-tournee.pdf")
          and "copie-de-securite.pdf" in o.text, "F12 remise impossible : verrou gardé avec les deux copies, message", short(o.text))
    shutil.rmtree(lk)

    interruptions(R)

    d = R.folder()
    C.make_pdf(f"{d}/date.pdf")
    bi = birth(f"{d}/date.pdf")
    o = R.run("+90", f"{d}/date.pdf", extra={"STAT_SHIFT_AFTER": "1"})
    check(any(a[-1] == str(bi) for a in o.dates) and "la date de creation a change" in o.text and o.rc == 1,
          "F12 date de création qui bouge : restaurée par osascript, sinon signalée", f"{o.dates} {short(o.text)}")
    d = R.folder()
    C.make_pdf(f"{d}/remise.pdf")
    bi = birth(f"{d}/remise.pdf")
    o = R.run("+90", f"{d}/remise.pdf", extra={"CMP_LIE": "1", "STAT_SHIFT_AFTER": "1"})
    check(any(a[-1] == str(bi) for a in o.dates) and "remis a l'identique" in o.text,
          "F12 remise à l'identique : la date de création d'avant est rétablie", f"{o.dates} {short(o.text)}")

    workflows(R)

    d = R.folder()
    C.make_pdf(f"{d}/é'\"\\ r.pdf")
    o = R.run("+90", f"{d}/é'\"\\ r.pdf")
    check(rotations(f"{d}/é'\"\\ r.pdf") == [90] and o.rc == 0, "section 5 nom exotique : tourné", short(o.stderr))


def content_kept(R):
    d = R.folder()
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 100))
    img = bytes((x * 7 + y * 3) % 256 for y in range(10) for x in range(60))
    xo = pikepdf.Stream(pdf, C.lzw(img))
    xo.Type, xo.Subtype, xo.Width, xo.Height = pikepdf.Name.XObject, pikepdf.Name.Image, 20, 10
    xo.ColorSpace, xo.BitsPerComponent, xo.Filter = pikepdf.Name.DeviceRGB, 8, pikepdf.Name.LZWDecode
    import io
    from PIL import Image
    buf = io.BytesIO()
    C.pattern(40, 20).save(buf, "JPEG", quality=90)
    jp = pikepdf.Stream(pdf, buf.getvalue())
    jp.Type, jp.Subtype, jp.Width, jp.Height = pikepdf.Name.XObject, pikepdf.Name.Image, 40, 20
    jp.ColorSpace, jp.BitsPerComponent, jp.Filter = pikepdf.Name.DeviceRGB, 8, pikepdf.Name.DCTDecode
    content = pikepdf.Stream(pdf, C.flate_level1(b"q 100 0 0 50 0 0 cm /Im0 Do Q q 40 0 0 20 0 50 cm /Im1 Do Q\n" * 20))
    content.Filter = pikepdf.Name.FlateDecode
    pdf.pages[0].Contents = content
    pdf.pages[0].Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=xo, Im1=jp))
    pdf.docinfo["/Title"] = "Bail"
    with pdf.open_outline() as outline:
        outline.root.append(pikepdf.OutlineItem("Chapitre", 0))
    pdf.attachments["note.txt"] = pikepdf.AttachedFileSpec(pdf, b"note")
    pdf.save(f"{d}/riche.pdf", compress_streams=False, stream_decode_level=pikepdf.StreamDecodeLevel.none)

    def state(path):
        with pikepdf.open(path) as p:
            pg = p.pages[0]
            res = pg.Resources.XObject
            decoded = [pg.obj.Contents.read_bytes(), res.Im0.read_bytes()]
            return (decoded, res.Im1.read_raw_bytes(), str(p.docinfo.get("/Title")), len(p.open_outline().root),
                    list(p.attachments.keys()), sorted(k for k in pg.obj.keys() if k != "/Rotate"))
    before = state(f"{d}/riche.pdf")
    R.run("+90", f"{d}/riche.pdf")
    after = state(f"{d}/riche.pdf")
    check(before == after and rotations(f"{d}/riche.pdf") == [90],
          "F12 contenu gardé : flux décodés égaux, JPEG à l'octet, titre, signet et pièce jointe, seul /Rotate change")


def interruptions(R):
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        d = R.folder()
        C.make_pdf(f"{d}/i.pdf", ["A", "B", "C"])
        before = C.sha(f"{d}/i.pdf")
        p, e, log = R.start("+90", f"{d}/i.pdf", extra={"CAT_MODE": "slow-rotated"})
        t0 = time.time()
        while not os.path.exists(e["CAT_MARK"]) and time.time() - t0 < 30:
            time.sleep(0.01)
        os.killpg(p.pid, sig)
        p.wait()
        lk = f"{d}/i.pdf.rotation-pdf-lock"
        ok = C.sha(f"{d}/i.pdf") == before or (os.path.exists(f"{lk}/copie-de-securite.pdf") and C.sha(f"{lk}/copie-de-securite.pdf") == before)
        check(ok and C.sha(f"{d}/i.pdf") == before and not locks(d),
              f"F12 {signal.Signals(sig).name} pendant la réécriture : original remis depuis la copie", f"{os.path.getsize(f'{d}/i.pdf')} {locks(d)}")
    d = R.folder()
    C.make_pdf(f"{d}/k.pdf", ["A", "B", "C"])
    before = C.sha(f"{d}/k.pdf")
    p, e, log = R.start("+90", f"{d}/k.pdf", extra={"CAT_MODE": "slow-rotated"})
    t0 = time.time()
    while not os.path.exists(e["CAT_MARK"]) and time.time() - t0 < 30:
        time.sleep(0.01)
    os.killpg(p.pid, signal.SIGKILL)
    p.wait()
    lk = f"{d}/k.pdf.rotation-pdf-lock"
    check(os.path.exists(f"{lk}/copie-de-securite.pdf") and C.sha(f"{lk}/copie-de-securite.pdf") == before,
          "F12 SIGKILL pendant la réécriture : le verrou garde une copie intacte")
    o = R.run("+90", f"{d}/k.pdf")
    t = o.text
    check("copie-de-securite.pdf" in t and t.find("ne s'ouvre pas") < t.find("supprimez") and t.find("ne s'ouvre pas") != -1,
          "F12 relance après SIGKILL : refus qui nomme la copie, remise avant suppression", short(t))
    d = R.folder()
    C.make_pdf(f"{d}/c.pdf", ["A", "B"])
    before = C.sha(f"{d}/c.pdf")
    p, e, log = R.start("+90", f"{d}/c.pdf", extra={"CP_MODE": "slow"})
    t0 = time.time()
    while not os.path.exists(e["CP_MARK"]) and time.time() - t0 < 30:
        time.sleep(0.01)
    os.killpg(p.pid, signal.SIGKILL)
    p.wait()
    lk = f"{d}/c.pdf.rotation-pdf-lock"
    partial = os.path.exists(f"{lk}/copie-de-securite.pdf") and C.sha(f"{lk}/copie-de-securite.pdf") != before
    o = R.run("+90", f"{d}/c.pdf")
    check(C.sha(f"{d}/c.pdf") == before and not partial and "copie-de-securite.pdf" not in o.text,
          "F12 copie de sécurité coupée par SIGKILL : jamais présentée comme intacte", short(o.text))


def workflows(R):
    home = os.path.join(R.base, "home")
    os.makedirs(f"{home}/Developer/scripts/services")
    os.symlink(SCRIPT, f"{home}/Developer/scripts/services/rotation-pdf.sh")
    for name, want in (("Rotation droite", 90), ("Rotation gauche", 270)):
        d = R.folder()
        C.make_pdf(f"{d}/mon fichier.pdf")
        e, log = R.env("")
        e.pop("ROTATE_ANGLE")
        e["HOME"] = home
        subprocess.run(["/bin/bash", "-c", C.command(name), "bash", f"{d}/mon fichier.pdf"], env=e, capture_output=True)
        check(rotations(f"{d}/mon fichier.pdf") == [want], f"F12 {name} : son script lance la rotation partagée ({want})",
              rotations(f"{d}/mon fichier.pdf"))
