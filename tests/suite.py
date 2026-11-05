"""VM suite of the services actions. Run it with tests/run.sh as a non-root user.
Usage: run.sh [--preconditions-only] [MODULE ...]   (modules: creer rotation connecteurs
sync structure selftest preuves_mac preconditions; all by default)"""
import os, signal, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common  # noqa: E402

MODULES = ["structure", "creer", "rotation", "connecteurs", "sync", "selftest", "preuves_mac", "preconditions"]


def stop(n, why):
    print(f"PRÉCONDITION ({n}) manquante : {why}", flush=True)
    sys.exit(2)


def preconditions():
    # (7) first: a launcher run in the background or under nohup inherits ignored signals,
    # which bash can no longer trap; the suite puts them back to their default for every child.
    for s in (signal.SIGINT, signal.SIGHUP, signal.SIGTERM):
        signal.signal(s, signal.SIG_DFL)
    probe = subprocess.run(["bash", "-c", 'trap "echo ok" INT; kill -INT $$'], capture_output=True, text=True)
    if probe.stdout.strip() != "ok":
        stop(7, "un script lancé par la suite ne peut pas piéger SIGINT (signal ignoré hérité)")
    print("INFO   sonde (7) : ok", flush=True)
    if os.geteuid() == 0:
        stop(1, "la suite tourne en root, qui écrit dans un dossier 0555 : lance-la sous un utilisateur ordinaire")
    prefix = os.environ.get("SUITE_PREFIX", common.PREFIX)
    try:
        v = subprocess.run([f"{prefix}/bin/qpdf", "--version"], capture_output=True, text=True).stdout.split()
        major = int(v[2].split(".")[0])
    except Exception:
        major = 0
    if major < 12:
        stop(2, f"{prefix}/bin/qpdf --version ne donne pas 12 ou plus")
    stat_cmd = os.environ.get("SUITE_STAT", "stat")
    probe_file = tempfile.NamedTemporaryFile(dir=os.environ.get("TMPDIR", "/tmp"))
    birth = subprocess.run([stat_cmd, "-c", "%W", probe_file.name], capture_output=True, text=True).stdout.strip()
    probe_file.close()
    if not birth.isdigit() or int(birth) == 0:
        stop(3, "le dossier de travail n'a pas de date de naissance (stat -c %W vaut 0)")
    if subprocess.run([f"{prefix}/bin/exiftool", "-ver"], capture_output=True).returncode:
        stop(5, f"{prefix}/bin/exiftool -ver ne répond pas (lien symbolique vers une autre installation ?)")
    bare = os.environ.get("SUITE_BARE_PATH", common.BARE_PATH)
    found = subprocess.run(["bash", "-c", "command -v qpdf exiftool img2pdf cjpeg"], capture_output=True, text=True,
                           env={"PATH": bare}).stdout.split()
    if found:
        stop(6, f"le PATH nu de l'action trouve {', '.join(found)}")


def main(argv):
    os.dup2(os.open(os.devnull, os.O_RDONLY), 0)  # a stand-in that reads stdin must never wait on ours
    only_pre = "--preconditions-only" in argv
    names = [a for a in argv if not a.startswith("--")] or MODULES
    preconditions()
    if only_pre:
        print("INFO   préconditions remplies")
        return 0
    os.environ["TZ"] = common.TZ
    for name in names:
        print(f"--- {name}", flush=True)
        mod = __import__(f"test_{name}")
        mod.main()
    ok, ko = common.results["ok"], common.results["ko"]
    print(f"Bilan suite : {ok} OK, {ko} ÉCHEC ({ok + ko} tests)")
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
