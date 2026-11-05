"""sync.sh (F15): links, duplicates, the Claude actions, brew and pbs, in a throwaway HOME and
a throwaway copy of the repository nested in a throwaway scripts repository, like on the Mac."""
import os, shutil, subprocess
import common as C
from common import check, short

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(cwd, *args):
    subprocess.run(["git", "-C", cwd, *args], check=True, capture_output=True, env={**os.environ, **GIT_ENV})


class Mac:
    """scripts/ (a git repo) holding services/ (its own git repo, a copy of this one)."""

    def __init__(self, base):
        self.scripts = os.path.join(base, "scripts")
        self.repo = os.path.join(self.scripts, "services")
        shutil.copytree(C.REPO, self.repo, ignore=shutil.ignore_patterns(".git", "__pycache__"), symlinks=True)
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "copy")
        os.makedirs(f"{self.scripts}/old/Ancien.workflow/Contents")
        open(f"{self.scripts}/old/Ancien.workflow/Contents/Info.plist", "w").write("ancien contenu")
        git(self.scripts, "init", "-q")
        git(self.scripts, "add", "old")
        git(self.scripts, "commit", "-qm", "old")
        self.home = os.path.join(base, "home")
        self.lib = os.path.join(self.home, "Library", "Services")
        os.makedirs(self.lib)
        self.workflows = sorted(n for n in os.listdir(self.repo) if n.endswith(".workflow"))

    def sync(self, script=None, env=None):
        e = {"HOME": self.home, "PATH": C.BARE_PATH}
        e.update(env or {})
        r = subprocess.run(["/bin/bash", script or f"{self.repo}/sync.sh"], env=e, capture_output=True, text=True)
        return r

    def links(self):
        return {n: (os.readlink(f"{self.lib}/{n}"), os.lstat(f"{self.lib}/{n}").st_ino)
                for n in os.listdir(self.lib) if os.path.islink(f"{self.lib}/{n}")}

    def variant(self, name, mapping):
        path = os.path.join(self.repo, name)
        C.write_exec(path, C.rewritten(open(f"{self.repo}/sync.sh").read(), mapping))
        return path


def main():
    base = C.scratch("sync-")
    m = Mac(base)
    r = m.sync()
    links = m.links()
    check(r.returncode == 0 and sorted(links) == m.workflows and all(t == f"{m.repo}/{n}" for n, (t, _) in links.items()),
          "F15 premier passage : un lien par workflow vers le dépôt", short(r.stdout + r.stderr))
    r = m.sync()
    check(r.returncode == 0 and m.links() == links and not r.stdout and not r.stderr,
          "F15 second passage : aucun lien changé, rien affiché", short(r.stdout + r.stderr))

    os.symlink(f"{m.scripts}/absent/Vieux.workflow", f"{m.lib}/Vieux.workflow")
    os.remove(f"{m.lib}/OCR sur PDF.workflow")
    shutil.copytree(f"{m.repo}/OCR sur PDF.workflow", f"{m.lib}/OCR sur PDF.workflow")
    os.remove(f"{m.lib}/Rotation gauche.workflow")
    os.symlink("/elsewhere/Rotation gauche.workflow", f"{m.lib}/Rotation gauche.workflow")
    r = m.sync()
    links = m.links()
    check(not os.path.lexists(f"{m.lib}/Vieux.workflow"), "F15 lien mort vers le dossier scripts : retiré", short(r.stdout))
    check(links.get("OCR sur PDF.workflow", ("",))[0] == f"{m.repo}/OCR sur PDF.workflow", "F15 copie réelle commitée : remplacée par un lien", short(r.stdout))
    check(links.get("Rotation gauche.workflow", ("",))[0] == f"{m.repo}/Rotation gauche.workflow", "F15 lien homonyme vers ailleurs : remplacé")
    check(r.returncode == 0, "F15 nettoyage sans problème : sortie 0", short(r.stderr))

    os.remove(f"{m.lib}/Créer un PDF.workflow")
    shutil.copytree(f"{m.repo}/Créer un PDF.workflow", f"{m.lib}/Créer un PDF.workflow")
    open(f"{m.lib}/Créer un PDF.workflow/Contents/notes.txt", "w").write("à moi")
    before = C.tree(f"{m.lib}/Créer un PDF.workflow")
    r = m.sync()
    check(r.returncode == 1 and "Créer un PDF.workflow" in r.stderr and C.tree(f"{m.lib}/Créer un PDF.workflow") == before,
          "F15 copie réelle que git ne connaît pas : gardée, signalée, sortie 1", short(r.stderr))
    shutil.rmtree(f"{m.lib}/Créer un PDF.workflow")
    m.sync()

    shutil.copytree(f"{m.scripts}/old/Ancien.workflow", f"{m.lib}/Ancien.workflow")
    r = m.sync()
    check(not os.path.exists(f"{m.lib}/Ancien.workflow") and "doublon retiré" in r.stdout,
          "F15 copie connue du seul dépôt scripts : retirée", short(r.stdout))

    os.makedirs(f"{m.lib}/Autre.workflow/Contents")
    open(f"{m.lib}/Autre.workflow/Contents/Info.plist", "w").write("autre")
    r = m.sync()
    check(os.path.exists(f"{m.lib}/Autre.workflow/Contents/Info.plist") and not r.stdout and not r.stderr and r.returncode == 0,
          "F15 autre action inconnue de git : intacte, rien affiché", short(r.stdout + r.stderr))
    os.makedirs(f"{m.lib}/Claude - ask.workflow/Contents")
    open(f"{m.lib}/Claude - ask.workflow/Contents/Info.plist", "w").write("claude")
    r = m.sync()
    check(os.path.exists(f"{m.lib}/Claude - ask.workflow/Contents/Info.plist") and "Claude" not in r.stdout + r.stderr and r.returncode == 0,
          "F15 Claude - ask inconnue de git : intacte, rien affiché", short(r.stdout + r.stderr))
    shutil.rmtree(f"{m.lib}/Claude - ask.workflow")
    for name in ("Claude - ask.workflow", "Claude - codeHere.workflow", "Claude - send.workflow"):
        for source in (f"{m.repo}/Rotation droite.workflow", f"{m.scripts}/old/Ancien.workflow"):
            shutil.copytree(source, f"{m.lib}/{name}")
            before = C.tree(f"{m.lib}/{name}")
            r = m.sync()
            check(os.path.isdir(f"{m.lib}/{name}") and C.tree(f"{m.lib}/{name}") == before and name not in r.stdout + r.stderr
                  and r.returncode == 0, f"F15 {name} dont git connaît les fichiers ({'dépôt' if 'services' in source else 'dépôt scripts'}) : intacte",
                  short(r.stdout + r.stderr))
            shutil.rmtree(f"{m.lib}/{name}")

    os.remove(f"{m.lib}/Rotation droite.workflow")
    shutil.move(f"{m.repo}/Rotation droite.workflow", f"{m.lib}/Rotation droite.workflow")
    r = m.sync()
    check(not os.path.lexists(f"{m.lib}/Rotation droite.workflow") and "doublon retiré (git le garde)" in r.stdout and r.returncode == 0,
          "F15 double-clic : la copie déplacée est retirée, aucun lien", short(r.stdout))
    git(m.repo, "restore", "Rotation droite.workflow")
    r = m.sync()
    check(os.path.islink(f"{m.lib}/Rotation droite.workflow"), "F15 après git restore : de nouveau relié", short(r.stdout))

    pbs_log = os.path.join(base, "pbs.log")
    pbs = C.write_exec(os.path.join(base, "pbs"), f'#!/bin/sh\necho "$@" >> "{pbs_log}"\nexit "${{PBS_RC:-0}}"\n')
    v = m.variant("sync-pbs.sh", {"/System/Library/CoreServices/pbs": pbs})
    m.sync(v)
    m.sync(v)
    calls = open(pbs_log).read().splitlines()
    check(calls == ["-flush", "-flush"], "F15 pbs -flush appelé une fois par passage, même sans changement", calls)
    r = m.sync(v, env={"PBS_RC": "1"})
    check(r.returncode == 0, "F15 pbs en erreur : sortie inchangée (0)", r.returncode)

    pre = os.path.join(base, "prefix")
    os.makedirs(f"{pre}/bin")
    os.makedirs(f"{pre}/opt/mozjpeg/bin")
    for t in ("qpdf", "img2pdf", "exiftool"):
        os.symlink(f"{C.PREFIX}/bin/{t}", f"{pre}/bin/{t}")
    os.symlink(f"{C.PREFIX}/opt/mozjpeg/bin/cjpeg", f"{pre}/opt/mozjpeg/bin/cjpeg")
    brew_log = os.path.join(base, "brew.log")
    open(brew_log, "w").close()
    C.write_exec(f"{pre}/bin/brew", f'#!/bin/sh\necho "$@" >> "{brew_log}"\n[ "$1" = install ] && ln -s {C.PREFIX}/bin/$2 {pre}/bin/$2\nexit 0\n')
    v = m.variant("sync-brew.sh", {"/opt/homebrew": pre})
    m.sync(v)
    m.sync(v)
    check(open(brew_log).read() == "", "F15 outils présents (mozjpeg seulement en keg) : brew jamais appelé", open(brew_log).read())
    os.remove(f"{pre}/bin/exiftool")
    r = m.sync(v)
    check(open(brew_log).read().splitlines() == ["install exiftool"] and r.returncode == 0,
          "F15 outil manquant : brew install appelé une fois, sortie 0", open(brew_log).read())
    os.remove(f"{pre}/bin/exiftool")
    os.remove(f"{pre}/bin/brew")
    r = m.sync(v)
    check(r.returncode == 1 and "manque et n'a pas pu être installé" in r.stderr, "F15 outil manquant sans brew : message, sortie 1", short(r.stderr))
