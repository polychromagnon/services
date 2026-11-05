"""preuves-mac.sh, run in the VM with the bench's stand-ins and a throwaway HOME (section 6)."""
import json, os, re, shutil, subprocess
import common as C
import test_rotation as TR
from common import check, short

EXPECTED = [("GESTE", "F1"), ("SAUTÉ", "F4"), ("SAUTÉ", "F9"), ("SAUTÉ", "F11"), ("SAUTÉ", "F12 rotation d'un PDF"),
            ("OK", "F12 scénarios"), ("SAUTÉ", "F12 les rotations"), ("OK", "F13 un nom"), ("GESTE", "F13 place"),
            ("SAUTÉ", "F14 metmux"), ("OK", "F14 un nom"), ("GESTE", "F15 menu"), ("SAUTÉ", "F15 une seule"), ("SAUTÉ", "section 4")]


def run(repo, base):
    home, tmp = os.path.join(base, "home"), os.path.join(base, "tmp")
    os.makedirs(home, exist_ok=True)
    os.makedirs(tmp, exist_ok=True)
    stat_dir = os.path.join(base, "stat")
    os.makedirs(stat_dir, exist_ok=True)
    C.write_exec(os.path.join(stat_dir, "stat"), TR.STAT)
    trace = os.path.join(base, "trace.jsonl")
    open(trace, "w").close()
    env = {"HOME": home, "PATH": "/usr/bin:/bin", "TMPDIR": tmp, "PREUVES_PATH_PREFIX": stat_dir, "PREUVES_TRACE": trace}
    r = subprocess.run(["/bin/bash", os.path.join(repo, "preuves-mac.sh")], env=env, capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l[:7].strip() in ("OK", "ÉCHEC", "GESTE", "SAUTÉ")]
    return r, lines, [json.loads(l) for l in open(trace)], home, tmp


def main():
    base = C.scratch("preuves-")
    home_before = None
    repo_before = C.tree(C.REPO)
    r, lines, trace, home, tmp = run(C.REPO, base)
    got = [(l[:7].strip(), l[7:]) for l in lines]
    ok = len(got) == len(EXPECTED) and all(s == es and t.startswith(et) for (s, t), (es, et) in zip(got, EXPECTED))
    check(ok, "section 6 preuves-mac.sh : une ligne par preuve et par geste [Mac], dans l'ordre du SPEC", [short(l, 80) for l in lines if not l.startswith(("OK", "SAUTÉ", "GESTE"))] or len(got))
    check(C.tree(C.REPO) == repo_before and C.tree(home) == {} and not os.listdir(tmp), "section 6 preuves-mac.sh : HOME et dépôt inchangés, rien ne reste",
          os.listdir(tmp))
    check(trace and all(t["launcher"] != t["scenario"] for t in trace), "section 6 signaux envoyés à un groupe de processus propre au scénario", trace)
    source = open(os.path.join(C.REPO, "tests", "preuves_mac.py")).read() + open(os.path.join(C.REPO, "preuves-mac.sh")).read()
    check(not re.search(r"\bsetsid\b", source), "section 6 aucun appel à setsid (absent de macOS)")
    copy = os.path.join(base, "copie")
    shutil.copytree(C.REPO, copy, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    p = os.path.join(copy, "tests", "preuves_mac.py")
    text = open(p).read()
    assert text.count("EXPECT_ROTATE = 90") == 1
    open(p, "w").write(text.replace("EXPECT_ROTATE = 90", "EXPECT_ROTATE = 91"))
    r, lines, trace, home, tmp = run(copy, os.path.join(base, "faux"))
    line = next((l for l in lines if "F12 scénarios" in l), "")
    check(line.startswith("ÉCHEC"), "section 6 une valeur attendue falsifiée donne ÉCHEC", short(line, 120))
