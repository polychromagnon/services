"""Mutation replay (SPEC section 5): each mutation, applied to a throwaway copy of the code the
suite runs, must make its named check fail. Run: bash tests/mutations.sh [NUMBER ...]"""
import os, plistlib, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CREER, EDIT, OCR = "Créer un PDF.workflow", "Éditer les métadonnées.workflow", "OCR sur PDF.workflow"

# (file, old text, new text, module, label of the check that must fail)
MUTATIONS = [
    (CREER, '"--stream-data=preserve"', '"--stream-data=compress"', "creer", "F2 flux Flate niveau 1 et image LZW"),
    (CREER, '"--stream-data=preserve"', '"--stream-data=compress", "--recompress-flate"', "creer", "F2 flux Flate niveau 1 et image LZW"),
    (CREER, '"-quality", "88"', '"-quality", "10"', "creer", "F4 HEIC : JPEG mozjpeg qualité 88"),
    (CREER, '"-sample", "2x2"', '"-sample", "1x1"', "creer", "F4 HEIC : JPEG mozjpeg qualité 88"),
    (CREER, "* 2 / mse) < 20:", "* 2 / mse) < 5:", "creer", "F4 seuil : 19 dB refusé"),
    (CREER, 'parse(rec.get("CreateDate"), since=1993)', "None", "creer", "F9 CreationDate de PDF seule plus ancienne"),
    (CREER, 't = parse(rec.get("ModifyDate"), since=1993)', "t = None", "creer", "F9 ModDate de PDF seule plus ancienne"),
    (CREER, 'parse(rec.get("CreateDate"), since=1993)', 'parse(rec.get("CreateDate"), since=1900)', "creer", "F9 dates PDF : 1980 et 1985 ignorées"),
    (CREER, 'parse(rec.get("CreateDate"), since=1993)', 'parse(rec.get("CreateDate"), since=1981)', "creer", "F9 dates PDF : 1992 ignorée"),
    (CREER, 't = parse(rec.get("ModifyDate"), since=1993)', 't = parse(rec.get("ModifyDate"), since=1986)', "creer", "F9 dates PDF : 1992 ignorée"),
    (CREER, "        pdf = img2pdf.convert(pngs, rotation=img2pdf.Rotation.none, layout_fun=a4_wide(False))",
     '        raise ValueError("seconde voie retirée")', "creer", "F6 seconde voie (logo.png)"),
    (CREER, 'notes.append(f"{what} non repris', 'notes.insert(0, f"{what} non repris', "creer", "F8 beaucoup de PDF"),
    (CREER, '    return not any(re.search(rb"(?<![\\d.])" + e + rb"\\b", t) for t in texts for e in empty)', "    return True",
     "creer", "F8 case vide utilisée (vide.pdf)"),
    (CREER, '            raise ValueError("TIFF mal lu par Pillow")', "            pass", "creer", "F6 TIFF non compressé couché en L"),
    (CREER, 'getattr(st, "st_birthtime", 0)', 'getattr(st, "st_birthtime", 1)', "creer", "F9 dates PDF : 1980 et 1985 ignorées"),
    (CREER, "for t in img2pdf qpdf exiftool mozjpeg; do", "for t in img2pdf qpdf mozjpeg; do", "creer", "F10 exiftool absent"),
    (CREER, 'dialog(f"« {os.path.basename(target)} » est créé, mais à vérifier :\\n" + "\\n".join(notes))',
     'dialog(f"« {os.path.basename(target)} » est créé, mais à vérifier :\\n" + notes[0]); [dialog(n) for n in notes[1:]]',
     "creer", "F8 une seule alerte par lancement"),
    (CREER, 'refuse(f"« {name} » n\'est pas un PDF lisible.")', 'refuse("Un fichier n\'est pas un PDF lisible.")', "creer", "F7 fake.pdf"),
    (CREER, "if len(pdf.pages) != expected:", "if False:", "creer", "F7 page perdue à l'assemblage"),
    (CREER, "            os.link(temp, target)", "            shutil.copyfile(temp, target)", "creer", "section 4 huit lancements simultanés"),
    (CREER, '                keep["dpi"] = keep["dpi"][::-1]', "                pass", "creer", "F5 matrice JPG"),
    (CREER, '            raise ValueError("TIFF turned across its diagonal")', "            pass", "creer", "F5 matrice TIF"),
    (CREER, "        signal.signal(s, stop)", "        pass", "creer", "section 5 arrêt par SIGTERM"),
    ("rotation-pdf.sh", '  touch -r "$rotated" -- "$pdf" 2>/dev/null', "  true", "rotation", "F12 Rotation droite : /Rotate 90, même inode, mêmes dates"),
    ("rotation-pdf.sh", '--rotate="${ROTATE_ANGLE}"', '--rotate="${ROTATE_ANGLE}:1"', "rotation", "F12 trois pages"),
    ("rotation-pdf.sh", '    if [ "${target_ids[$i]}" = "$identity" ]; then', "    if false; then", "rotation", "F12 dossier, fichier et lien"),
    ("rotation-pdf.sh", '  identity=$(file_identity "$candidate")', '  identity="$candidate"', "rotation", "F12 dossier, fichier et lien"),
    ("rotation-pdf.sh", '      *) restore_creation_date "$pdf" "$birth_before" ;;', "      *) : ;;", "rotation", "F12 date de création qui bouge"),
    ("rotation-pdf.sh", '      *) restore_creation_date "$target" "$birth" ;;', "      *) : ;;", "rotation", "F12 remise à l'identique : la date de création"),
    ("rotation-pdf.sh", 'cp -p -- "$pdf" "$lockdir/copie-en-cours" && mv -- "$lockdir/copie-en-cours" "$backup"', 'cp -p -- "$pdf" "$backup"',
     "rotation", "F12 copie de sécurité coupée par SIGKILL"),
    ("rotation-pdf.sh", '  if [ -n "$rewriting" ]; then', "  if false; then", "rotation", "F12 SIGTERM pendant la réécriture"),
    ("rotation-pdf.sh", '    if [ -f "$lockdir/copie-de-securite.pdf" ]; then', "    if false; then", "rotation", "F12 verrou qui garde la copie"),
    ("sync.sh", '  [ "$t" = mozjpeg ] && p=/opt/homebrew/opt/mozjpeg/bin/cjpeg  # keg-only: never in bin', "", "sync", "F15 outils présents"),
    ("sync.sh", '"Claude - ask.workflow"|"Claude - codeHere.workflow"|"Claude - send.workflow") continue ;;', '"Claude - aucune") continue ;;',
     "sync", "F15 Claude - ask.workflow dont git"),
    ("sync.sh", '"Claude - ask.workflow"|"Claude - codeHere.workflow"|"Claude - send.workflow") continue ;;', '"Claude - ask.workflow") continue ;;',
     "sync", "F15 Claude - codeHere.workflow dont git"),
    ("sync.sh", ' || git -C "$SCRIPTS" cat-file -e "$h" 2>/dev/null', "", "sync", "F15 copie connue du seul dépôt scripts"),
    ("sync.sh", "  local f h\n", "  return 0\n  local f h\n", "sync", "F15 copie réelle que git ne connaît pas"),
    (EDIT, """files="$files $(LC_ALL=C printf '%q' "$f")\"""", 'files="$files $f"', "connecteurs", "F13 noms exotiques"),
    (EDIT, "for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 python3 python; do",
     "for c in /usr/local/bin/python3 /opt/homebrew/bin/python3 python3 python; do", "connecteurs", "F13 ordre des Python"),
    (OCR, """cmd="printf '\\\\033[H\\\\033[2J\\\\033[3J'; $(shell_quote "$PYTHON_BIN") $(shell_quote "$VIEW_SCRIPT")\"""",
     """cmd="$(shell_quote "$PYTHON_BIN") $(shell_quote "$VIEW_SCRIPT")\"""", "connecteurs", "F14 une seule fenêtre"),
    (OCR, "as_cmd=${cmd//\\\\/\\\\\\\\}", "as_cmd=$cmd", "connecteurs", "F14 une seule fenêtre"),
]


def code_count(text, old):
    """Occurrences of old once comment lines are left out (shell and Python both comment with #)."""
    return "".join(l for l in text.splitlines(keepends=True) if not l.lstrip().startswith("#")).count(old)


def apply(copy, target, old, new):
    if target.endswith(".workflow"):
        doc = os.path.join(copy, target, "Contents", "document.wflow")
        p = plistlib.load(open(doc, "rb"))
        (ap,) = [a["action"]["ActionParameters"] for a in p["actions"] if "COMMAND_STRING" in a["action"]["ActionParameters"]]
        text = ap["COMMAND_STRING"]
    else:
        text = open(os.path.join(copy, target)).read()
    if old == new or text.count(old) != 1 or code_count(text, old) != 1:
        return f"texte introuvable ou pas exactement une fois hors commentaire ({text.count(old)})"
    text = text.replace(old, new)
    if target.endswith(".workflow"):
        ap["COMMAND_STRING"] = text
        plistlib.dump(p, open(doc, "wb"))
    else:
        open(os.path.join(copy, target), "w").write(text)
    return None


def main(argv):
    picks = [int(a) for a in argv] or range(1, len(MUTATIONS) + 1)
    caught = total = 0
    for n in picks:
        target, old, new, module, label = MUTATIONS[n - 1]
        total += 1
        copy = tempfile.mkdtemp(prefix=f"mutation{n}-")
        shutil.copytree(REPO, copy, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        refused = apply(copy, target, old, new)
        if refused:
            print(f"ÉCHEC  mutation {n} ({target}) refusée : {refused}", flush=True)
            shutil.rmtree(copy, ignore_errors=True)
            continue
        r = subprocess.run(["bash", os.path.join(copy, "tests", "run.sh"), module], capture_output=True, text=True)
        hit = any(l.startswith("ÉCHEC  " + label) for l in r.stdout.splitlines())
        caught += hit
        print(("OK     " if hit else "ÉCHEC  ") + f"mutation {n} ({target}) : « {label} » " + ("en ÉCHEC" if hit else "reste vert"), flush=True)
        shutil.rmtree(copy, ignore_errors=True)
    print(f"Bilan mutations : {caught} attrapées sur {total}")
    return 0 if caught == total else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
