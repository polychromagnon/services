"""F11: the Mac self-test, judged in the VM against the reference list of its 38 checks."""
import os, re, shutil, subprocess
import common as C
from common import check, short

REF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selftest-vm-attendu.txt")
DATE_ONLY = re.compile(r"\(« [^»]+ » est créé, mais à vérifier : la date de création du fichier n'a pas pu être recalée\)$")


def reference():
    out = []
    for line in open(REF):
        if line.startswith("#") or not line.strip():
            continue
        status, label = line.rstrip("\n").split("\t")
        out.append((status, label))
    return out


def matches(line, label):
    return line == label or line.startswith(label + " (")


def run_selftest(repo, home, tmp):
    env = {"HOME": home, "PATH": "/usr/bin:/bin", "TMPDIR": tmp}
    return subprocess.run(["/bin/bash", f"{repo}/test-creer-pdf.sh"], env=env, capture_output=True, text=True)


def main():
    base = C.scratch("selftest-")
    home, tmp = os.path.join(base, "home"), os.path.join(base, "tmp")
    os.makedirs(home)
    os.makedirs(tmp)
    repo_before, home_before = C.tree(C.REPO), C.tree(home)
    r = run_selftest(C.REPO, home, tmp)
    lines = r.stdout.splitlines()
    checks = [l for l in lines if l.startswith(("OK     ", "ÉCHEC  "))]
    check(bool(lines) and re.match(r"^INFO   img2pdf \S+, pikepdf \S+, Pillow \S+, Python \S+$", lines[0]) is not None,
          "F11 première ligne : les quatre versions", lines[0] if lines else "")
    check(bool(lines) and re.match(r"^Bilan : \d+ OK, \d+ ÉCHEC$", lines[-1]) is not None, "F11 dernière ligne : le bilan", lines[-1] if lines else "")
    ref = reference()
    got = [("OK" if l.startswith("OK") else "ÉCHEC", l[7:]) for l in checks]
    same = len(got) == len(ref) and all(s == rs and matches(t, rl) for (s, t), (rs, rl) in zip(got, ref))
    first_diff = next(((g, w) for g, w in zip(got, ref) if g[0] != w[0] or not matches(g[1], w[1])), None)
    check(same, "F11 intitulés et statuts dans la VM : exactement ceux du fichier de référence (38 contrôles, 6 ÉCHEC attendus)",
          f"{len(got)} lignes, premier écart {first_diff}")
    date_lines = [t for s, t in got if s == "ÉCHEC" and not t.startswith(("HEIC : photo d'essai introuvable", "date de création = prise de vue"))]
    check(len(date_lines) == 4 and all(DATE_ONLY.search(t) for t in date_lines),
          "F11 les quatre ÉCHEC « sans alerte » ne portent que l'alerte de date de création", [short(t, 90) for t in date_lines])
    check(r.returncode == 0, "F11 code de sortie 0", r.returncode)
    moved = C.changed(repo_before, C.tree(C.REPO)) + C.changed(home_before, C.tree(home)) + os.listdir(tmp)
    check(not moved, "F11 rien touché hors de son dossier temporaire, qui a disparu", moved)

    copy = os.path.join(base, "copie")
    shutil.copytree(C.REPO, copy, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    import plistlib
    doc = f"{copy}/Créer un PDF.workflow/Contents/document.wflow"
    p = plistlib.load(open(doc, "rb"))
    for a in p["actions"]:
        ap = a["action"]["ActionParameters"]
        if "COMMAND_STRING" in ap:
            assert ap["COMMAND_STRING"].count("Impossible d'écrire dans") >= 1
            ap["COMMAND_STRING"] = ap["COMMAND_STRING"].replace("Impossible d'écrire dans", "Écriture refusée dans")
    plistlib.dump(p, open(doc, "wb"))
    r = run_selftest(copy, home, tmp)
    line = next((l for l in r.stdout.splitlines() if "dossier protégé en écriture" in l), "")
    check(line.startswith("ÉCHEC") and r.stdout.rstrip().endswith("Bilan : 31 OK, 7 ÉCHEC"),
          "F11 le self-test exécute le script de document.wflow : un message changé fait échouer sa ligne", short(line, 120))
