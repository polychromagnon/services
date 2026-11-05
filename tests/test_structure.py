"""Checks by reading: menus and icons (F16), forbidden strings and bash 3.2 syntax (section 3),
the shell actions' wiring (F12, F16), the order of the date calls (section 4)."""
import glob, os, re
from common import REPO, check, command, plist, shell_actions

ICON_KEYS = ("NSIconName", "NSBackgroundColorName", "systemImageName", "backgroundColorName")
MENUS = {
    "Créer un PDF": ["com.adobe.pdf", "public.image"],
    "OCR sur PDF": ["com.adobe.pdf", "public.folder"],
    "Rotation droite": ["com.adobe.pdf", "public.folder"],
    "Rotation gauche": ["public.item"],
    "Éditer les métadonnées": ["public.item"],
}


def keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from keys(v)


def code_lines(text):
    """Lines without their comment part (shell and Python both use #)."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        out.append(re.sub(r"\s#\s.*$", "", line))
    return out


def scripts():
    texts = {os.path.basename(p): open(p).read() for p in glob.glob(os.path.join(REPO, "*.sh"))}
    for name in MENUS:
        for i, ap in enumerate(shell_actions(name)):
            texts[f"{name} (COMMAND_STRING)"] = ap["COMMAND_STRING"]
    return texts


def guarded(lines, at, name):
    """True when line `at` sits inside an `if` testing ${#name[@]} -gt 0."""
    depth = 0
    for i in range(at, -1, -1):
        s = lines[i].strip()
        if re.match(r"fi\b", s) and i != at:
            depth += 1
        elif re.match(r"if\b", s):
            if depth == 0:
                if f"${{#{name}[@]}}" in s and "-gt 0" in s:
                    return True
            else:
                depth -= 1
    return False


def main():
    for name, types in MENUS.items():
        svc = plist(name, "Info.plist")["NSServices"][0]
        check(svc["NSMenuItem"]["default"] == name and svc["NSSendFileTypes"] == types,
              f"F16 {name} : nom de menu et types de fichiers", f"{svc['NSMenuItem']} {svc['NSSendFileTypes']}")
        found = set(keys(plist(name, "Info.plist"))) | set(keys(plist(name, "document.wflow")))
        icons = sorted(found & set(ICON_KEYS))
        if name == "Rotation gauche":
            check("NSIconName" in icons and "systemImageName" in icons, "F16 Rotation gauche : porte une icône", icons)
        else:
            check(not icons, f"F16 {name} : aucune clé d'icône", icons)
        for ap in shell_actions(name):
            check(ap.get("inputMethod") == 1, f"F16 {name} : les fichiers arrivent en arguments (inputMethod 1)", ap.get("inputMethod"))

    for name, angle in (("Rotation gauche", "-90"), ("Rotation droite", "+90")):
        acts = plist(name, "document.wflow")["actions"]
        shell = [i for i, a in enumerate(acts) if "COMMAND_STRING" in a["action"]["ActionParameters"]]
        cmd = command(name)
        check(shell == [3] and f'ROTATE_ANGLE="{angle}"' in cmd and '"$HOME/Developer/scripts/services/rotation-pdf.sh"' in cmd,
              f"F12 {name} : quatrième action, ROTATE_ANGLE {angle}, script partagé par $HOME/Developer/scripts/services", short_cmd(cmd))

    menu = []
    for d, dirs, files in os.walk(REPO):
        dirs[:] = [x for x in dirs if x != ".git"]
        for n in files:
            if n.endswith(".md"):
                continue
            p = os.path.join(d, n)
            try:
                text = open(p, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            if any(line.startswith("# menu:") for line in text.splitlines()):
                menu.append(os.path.relpath(p, REPO))
    check(not menu, "F16 aucun fichier hors .md n'a d'en-tête « # menu: »", menu)

    texts = scripts()
    for word, label in (("regen_quickaction", "section 3 : regen_quickaction n'est appelé nulle part"),
                        ("get_images", "section 3 : aucun appel à get_images (pikepdf 10.9+)")):
        hits = [n for n, t in texts.items() if any(word in line for line in code_lines(t))]
        check(not hits, label, hits)
    rot = open(os.path.join(REPO, "rotation-pdf.sh")).read()
    check(not any("replace-input" in line for line in code_lines(rot)), "section 3 : la rotation n'emploie jamais --replace-input")

    users = []
    for n in ("Éditer les métadonnées", "OCR sur PDF"):
        for line in code_lines(command(n)):
            if re.search(r"/Users/michael/Developer/(metmux|ocrswap)/", line):
                users.append(line.strip())
    want = ['METMUX="/Users/michael/Developer/metmux/metmux.py"',
            'PYTHON_BIN="/Users/michael/Developer/ocrswap/.venv/bin/python3"',
            'VIEW_SCRIPT="/Users/michael/Developer/ocrswap/ocrswap.py"']
    check(users == want, "section 3, F13, F14 : seules les trois constantes visent les dépôts metmux et ocrswap", users)
    writers = [l for n in ("Éditer les métadonnées", "OCR sur PDF") for l in code_lines(command(n))
               if re.search(r"(>|\bcp\b|\bmv\b|\brm\b|\bgit\b|\btouch\b).*\$(METMUX|PYTHON_BIN|VIEW_SCRIPT)", l)]
    check(not writers, "section 3 : aucune écriture vers les dépôts metmux et ocrswap", writers)

    lines = rot.splitlines()
    bad = []
    for i, line in enumerate(lines):
        for name in re.findall(r'"\$\{(\w+)\[@\]\}"', line):
            if not guarded(lines, i, name):
                bad.append(f"{i + 1}:{name}")
    check(not bad, "section 3 bash 3.2 : aucun tableau peut-être vide développé hors d'un test ${#T[@]} -gt 0", bad)
    bash4 = [r"declare -A", r"\bmapfile\b", r"\breadarray\b", r"\$\{\w+,,\}", r"\$\{\w+\^\^\}", r"\|&", r"&>>", r";&",
             r"\bcoproc\b", r"\$BASHPID", r"wait -n", r"local -n", r"\[\[ -v", r"\$EPOCHSECONDS", r"\$EPOCHREALTIME",
             r"\$\{\w+@Q\}", r"read -t [0-9]*\.", r"declare -g", r"%\(.*\)T", r"\[-1\]\}"]
    hits = [(i + 1, p) for i, line in enumerate(code_lines(rot)) for p in bash4 if re.search(p, line)]
    check(not hits, "section 3 bash 3.2 : aucune syntaxe propre à bash 4 ou plus dans la rotation", hits)

    jxa = command("Créer un PDF")
    m, c = jxa.find("NSFileModificationDate"), jxa.find("NSFileCreationDate")
    check(0 < m < c, "section 4 : l'action pose la date de modification avant la date de création")
    check("open(target, \"xb\")" in jxa and "os.link(temp, target)" in jxa and "except FileExistsError" in jxa,
          "section 4 : nom final réservé par lien dur exclusif, repli par création exclusive")


def short_cmd(c):
    return " ".join(c.split())[:160]
