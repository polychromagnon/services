"""Éditer les métadonnées (F13) and OCR sur PDF (F14), with fake metmux and ocrswap repositories."""
import json, os, re, subprocess, sys
import common as C
from common import check, short

OSASCRIPT = r'''#!/usr/bin/python3
import json, os, sys
with open(os.environ["OSA_LOG"], "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "stdin": sys.stdin.read() if not sys.stdin.isatty() else ""}) + "\n")
'''

RECORDER = '''import json, os, sys
with open(os.environ["ARGV_LOG"], "w") as f:
    json.dump({"exe": sys.executable, "argv": sys.argv[1:]}, f)
'''

PATHS = ["a b.pdf", "l'été.pdf", 'dit "oui".pdf', "back\\slash.pdf"]


def unescape_applescript(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            out.append(s[i + 1])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def main():
    base = C.scratch("connecteurs-")
    bin_ = os.path.join(base, "bin")
    os.makedirs(bin_)
    C.write_exec(os.path.join(bin_, "osascript"), OSASCRIPT)
    docs = os.path.join(base, "docs")
    os.makedirs(docs)
    files = [os.path.join(docs, n) for n in PATHS]
    for f in files:
        open(f, "w").write("x")

    metmux_repo = os.path.join(base, "metmux")
    os.makedirs(metmux_repo)
    open(f"{metmux_repo}/metmux.py", "w").write(RECORDER)
    ocr_repo = os.path.join(base, "ocrswap")
    os.makedirs(f"{ocr_repo}/.venv/bin")
    os.symlink(sys.executable, f"{ocr_repo}/.venv/bin/python3")
    open(f"{ocr_repo}/ocrswap.py", "w").write(RECORDER)
    repos_before = (C.tree(metmux_repo), C.tree(ocr_repo))

    def run(script, args, path=None, env=None):
        log = os.path.join(base, f"osa{len(os.listdir(base))}.log")
        open(log, "w").close()
        e = {"PATH": path or f"{bin_}:{C.BARE_PATH}", "OSA_LOG": log, "HOME": os.environ["HOME"]}
        e.update(env or {})
        r = subprocess.run(["/bin/bash", "-c", script, "bash", *args], env=e, capture_output=True, text=True)
        calls = [json.loads(line) for line in open(log)]
        return r, calls

    # --- F13 -----------------------------------------------------------------------------
    edit = C.command("Éditer les métadonnées")
    copy = C.rewritten(edit, {"/Users/michael/Developer/metmux/metmux.py": f"{metmux_repo}/metmux.py"})
    r, calls = run(copy, files)
    cmd = calls[0]["argv"][1] if calls else ""
    argv_log = os.path.join(base, "argv.json")
    subprocess.run(["zsh", "-c", cmd], env={"PATH": C.BARE_PATH, "ARGV_LOG": argv_log}, capture_output=True)
    got = json.load(open(argv_log)) if os.path.exists(argv_log) else {}
    check(r.returncode == 0 and len(calls) == 1 and got.get("argv") == ["--mode=ask", *files],
          "F13 noms exotiques : rejoués par zsh, metmux reçoit exactement les chemins après --mode=ask", short(got))
    check("-" == (calls[0]["argv"][0] if calls else "") and cmd not in (calls[0]["stdin"] if calls else ""),
          "F13 la commande passe à osascript en argument, jamais dans le texte AppleScript")
    import shutil
    first = next(p for p in ["/opt/homebrew/bin/python3", "/usr/local/bin/python3",
                             shutil.which("python3", path=C.BARE_PATH), shutil.which("python", path=C.BARE_PATH)] if p and os.access(p, os.X_OK))
    check(cmd.split("; ", 1)[-1].startswith(first + " ") and got.get("exe") == first,
          "F13 metmux lancé par le premier Python présent", f"{first} {got.get('exe')}")

    fake = os.path.join(base, "pythons")
    for sub in ("hb", "ul", "path3", "path"):
        os.makedirs(f"{fake}/{sub}")
    order_copy = C.rewritten(copy, {"/opt/homebrew/bin/python3": f"{fake}/hb/python3", "/usr/local/bin/python3": f"{fake}/ul/python3"})
    cands = [f"{fake}/hb/python3", f"{fake}/ul/python3", f"{fake}/path3/python3", f"{fake}/path/python"]
    for c in cands:
        C.write_exec(c, "#!/bin/sh\necho fake\n")
    path = f"{bin_}:{fake}/path3:{fake}/path"
    seq = []
    for k in range(4):
        r, calls = run(order_copy, files[:1], path=path)
        cmd = calls[0]["argv"][1] if calls else ""
        chosen = next((c for c in cands if c in cmd), None)
        seq.append(chosen)
        os.remove(cands[k])
    check(seq == cands, "F13 ordre des Python : Homebrew, /usr/local, python3, python", seq)
    r, calls = run(order_copy, files[:1], path=path)
    text = " ".join(" ".join(c["argv"]) for c in calls)
    check(r.returncode == 1 and "Python 3 est introuvable" in text, "F13 aucun Python : dialogue, sortie 1", short(text))
    missing = C.rewritten(edit, {"/Users/michael/Developer/metmux/metmux.py": f"{base}/absent/metmux.py"})
    r, calls = run(missing, files[:1])
    text = " ".join(" ".join(c["argv"]) for c in calls)
    check(r.returncode == 1 and "metmux.py est introuvable" in text, "F13 metmux absent : dialogue, sortie 1", short(text))

    # --- F14 -----------------------------------------------------------------------------
    ocr = C.command("OCR sur PDF")
    copy = C.rewritten(ocr, {"/Users/michael/Developer/ocrswap/.venv/bin/python3": f"{ocr_repo}/.venv/bin/python3",
                             "/Users/michael/Developer/ocrswap/ocrswap.py": f"{ocr_repo}/ocrswap.py"})
    three = files[1:]
    r, calls = run(copy, three)
    scripts = [a for c in calls for a in c["argv"] if "do script" in a]
    cmd = ""
    if len(scripts) == 1:
        m = re.match(r'tell application "Terminal" to do script "(.*)"$', scripts[0], re.S)
        cmd = unescape_applescript(m.group(1)) if m else ""
    if os.path.exists(argv_log):
        os.remove(argv_log)
    out = subprocess.run(["zsh", "-c", cmd], env={"PATH": C.BARE_PATH, "ARGV_LOG": argv_log}, capture_output=True)
    got = json.load(open(argv_log)) if os.path.exists(argv_log) else {}
    check(len(scripts) == 1 and out.stdout.startswith(b"\x1b[H\x1b[2J\x1b[3J") and got.get("argv") == three,
          "F14 une seule fenêtre : effacement puis ocrswap reçoit exactement les trois chemins", short(got))
    r, calls = run(copy, [])
    check(r.returncode == 0 and not calls, "F14 sans sélection : rien")

    check((C.tree(metmux_repo), C.tree(ocr_repo)) == repos_before, "section 3 dépôts metmux et ocrswap inchangés")
