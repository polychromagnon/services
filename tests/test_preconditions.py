"""Section 1: each precondition, violated on purpose, stops the suite before any check."""
import os, shutil, subprocess
import common as C
from common import check, short

RUN = os.path.join(C.REPO, "tests", "run.sh")


def suite(env=None, wrapper=None, run=RUN):
    e = {**os.environ, **(env or {})}
    cmd = ["bash", run, "--preconditions-only"]
    if wrapper:
        cmd = wrapper + cmd
    r = subprocess.run(cmd, env=e, capture_output=True, text=True)
    out = r.stdout + r.stderr
    return r.returncode, out, not any(l.startswith(("OK ", "ÉCHEC ")) for l in out.splitlines())


def prefix(base, name, broken):
    pre = os.path.join(base, name)
    os.makedirs(f"{pre}/bin")
    for t in ("qpdf", "img2pdf", "exiftool"):
        os.symlink(f"{C.PREFIX}/bin/{t}", f"{pre}/bin/{t}")
    os.remove(f"{pre}/bin/{broken[0]}")
    broken[1](f"{pre}/bin/{broken[0]}")
    return pre


def main():
    base = C.scratch("preconditions-")
    rc, out, clean = suite()
    check(rc == 0 and "préconditions remplies" in out, "section 1 préconditions remplies sur le banc", short(out))
    rc, out, clean = suite(wrapper=["unshare", "-r"])
    check(rc != 0 and "PRÉCONDITION (1)" in out and clean, "section 1 (1) en root : arrêt nommé", short(out))
    old = C.write_exec(os.path.join(base, "qpdf-11"), "#!/bin/sh\necho 'qpdf version 11.3.0'\n")
    pre = prefix(base, "p2", ("qpdf", lambda p: os.symlink(old, p)))
    rc, out, clean = suite({"SUITE_PREFIX": pre})
    check(rc != 0 and "PRÉCONDITION (2)" in out and clean, "section 1 (2) qpdf 11.3 : arrêt nommé", short(out))
    zero = C.write_exec(os.path.join(base, "stat0"), "#!/bin/sh\necho 0\n")
    rc, out, clean = suite({"SUITE_STAT": zero})
    check(rc != 0 and "PRÉCONDITION (3)" in out and clean, "section 1 (3) dossier sans date de naissance : arrêt nommé", short(out))
    failing = C.write_exec(os.path.join(base, "exiftool-casse"), "#!/bin/sh\nexit 1\n")
    pre = prefix(base, "p5", ("exiftool", lambda p: os.symlink(failing, p)))
    rc, out, clean = suite({"SUITE_PREFIX": pre})
    check(rc != 0 and "PRÉCONDITION (5)" in out and clean, "section 1 (5) exiftool en lien qui échoue : arrêt nommé", short(out))
    bare = os.path.join(base, "nu")
    os.makedirs(bare)
    os.symlink(f"{C.PREFIX}/opt/mozjpeg/bin/cjpeg", f"{bare}/cjpeg")
    rc, out, clean = suite({"SUITE_BARE_PATH": f"{bare}:{C.BARE_PATH}"})
    check(rc != 0 and "PRÉCONDITION (6)" in out and clean, "section 1 (6) cjpeg dans le PATH nu : arrêt nommé", short(out))
    rc, out, clean = suite(wrapper=["bash", "-c", 'trap "" INT; exec "$0" "$@"'])
    check(rc == 0 and "sonde (7) : ok" in out, "section 1 (7) suite lancée avec SIGINT ignoré : le lanceur remet les signaux, la sonde répond", short(out))
    copy = os.path.join(base, "copie")
    shutil.copytree(os.path.join(C.REPO, "tests"), copy, ignore=shutil.ignore_patterns("__pycache__"))
    p = os.path.join(copy, "suite.py")
    text = open(p).read()
    line = "        signal.signal(s, signal.SIG_DFL)\n"
    assert text.count(line) == 1
    open(p, "w").write(text.replace(line, "        pass\n"))
    rc, out, clean = suite(wrapper=["bash", "-c", 'trap "" INT; exec "$0" "$@"'], run=os.path.join(copy, "run.sh"))
    check(rc != 0 and "PRÉCONDITION (7)" in out and clean, "section 1 (7) lanceur qui ne remet pas les signaux : arrêt nommé", short(out))
