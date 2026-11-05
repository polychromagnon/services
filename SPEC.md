# SPEC — services (actions Finder de Michael)

> **Le principe.** Tu donnes des coordonnées : où aller, ce que ça fait, par où ne pas passer, et **comment on prouve qu'on y est**. L'équipe conduit ; tout ce que tu ne figes pas ici, elle est libre de le décider et tenue d'en faire la meilleure version.
>
> **Règle d'or — rien ne s'affirme sans sa preuve.** Chaque fonctionnalité et chaque interdiction porte sa preuve juste à côté ; une preuve qui relie plusieurs fonctionnalités va dans les Risques d'interaction ; une preuve qui vaut partout va dans les Tests de robustesse. Une preuve = un fait vérifiable = un test.
>
> **Marquage.** `> à vérifier —` préfixe ce que dev a déduit sans que Michael l'ait dit. Les décisions ouvertes vivent dans `BARRE.md`.
>
> **Origine de ce SPEC (2026-11-05, `/dev auto +++`, Michael absent).** Aucun besoin nouveau n'était écrit pour ce cycle. Ce SPEC fige donc le comportement que Michael a déjà décidé, tel que le `CLAUDE.md` du dépôt le consigne avec ses dates, et le code qui le porte : le cycle prouve l'existant, il n'ajoute aucune fonctionnalité (décidé par dev en l'absence du PO, à revoir). Les décisions datées citées viennent du `CLAUDE.md` ; le code est la deuxième source.

---

## 1. Description globale — ce que fait le code

Ce dépôt est la seule source des actions rapides du Finder de Michael (clic droit sur des fichiers, sur son MacBook Air M3, macOS Tahoe, outils Homebrew sous `/opt/homebrew`). Michael ne code pas : il veut des actions qui ne lui font jamais perdre une donnée et qui le préviennent quand un résultat ne peut pas être garanti. Cinq actions et deux outils :

- **Créer un PDF** : assemble les PDF et images sélectionnés, dans l'ordre des clics, en un seul PDF posé à côté du premier fichier, sans toucher aux originaux ; pages PDF recopiées à l'octet, images prouvées identiques avant usage, photos HEIC (et formats que seul macOS lit) converties en JPEG à peu près du poids du HEIC ; dates les plus anciennes reprises ; alertes quand le résultat perd quelque chose.
- **Rotation gauche** et **Rotation droite** : tournent de 90° les pages de PDF (ou des PDF d'un dossier) en place, en gardant l'identité du fichier.
- **Éditer les métadonnées** : connecteur qui ouvre metmux (`/Users/michael/Developer/metmux/metmux.py`, lu, jamais modifié) dans Terminal sur la sélection.
- **OCR sur PDF** : connecteur qui ouvre ocrswap (`/Users/michael/Developer/ocrswap`, lu, jamais modifié) dans une seule fenêtre Terminal pour toute la sélection.
- **`sync.sh`** : relie chaque action du dépôt dans `~/Library/Services` (une modification s'applique aussitôt) et nettoie les doublons.
- **`test-creer-pdf.sh`** : self-test de Créer un PDF sur le Mac, que `maj` relance quand un outil change.

**Domaines sensibles** : fichiers (originaux de Michael, écriture en place de la rotation, copies dans `~/Library/Services`), dates et fuseaux (dates de création et de modification, dates EXIF et PDF), encodage (noms avec accents, apostrophes, guillemets, espaces passés à osascript et Terminal), couleurs (profils ICC), concurrence (deux lancements simultanés).

**Plateforme et limite du banc.** Le produit tourne sur macOS. Le banc de la VM (décrit dans `CLAUDE.md`, « VM bench ») imite le Mac par des doublures de `sips`, `plutil` et `osascript` ; il ne sait pas poser une date de création ni lancer Terminal. Chaque preuve ci-dessous dit si elle se rejoue dans la VM ou seulement sur le Mac (`[Mac]`).

## 2. Fonctionnalités attendues + preuves

### F1. Créer un PDF : un seul PDF, ordre des clics, nom à la Apple
- **Quoi** — Les PDF et images sélectionnés deviennent un seul PDF, pages dans l'ordre des clics, posé dans le dossier du premier fichier et nommé comme le fait Apple : `doc1.pdf`, ou `doc1 2.pdf`, `doc1 3.pdf`… quand le nom est pris.
- **Preuve** — Sélection `a.pdf` (2 pages), `photo.jpg`, `capture.png`, `b.pdf` (1 page) avec `a.pdf` présent : exactement un fichier nouveau, `a 2.pdf`, de 5 pages, dont les pages 1, 2 et 5 ont les contenus de `a.pdf` p1, p2 et `b.pdf` p1 (sinon c'est faux).
- **Preuve** — Avec `b 2.pdf` déjà présent, l'action sur `b.pdf` crée `b 3.pdf` et rien d'autre.

### F2. Pages PDF recopiées à l'octet
- **Quoi** — Chaque page d'un PDF source passe dans le PDF créé sans que ses flux soient décodés ni recompressés (qpdf `--stream-data=preserve`).
- **Preuve** — Pour chaque page PDF du résultat, les octets bruts de son flux de contenu égalent ceux de la page source (comparaison `read_raw_bytes`), dans l'ordre des clics.

### F3. Images insérées sans perte
- **Quoi** — JPEG, PNG, GIF, BMP, WebP et `.tif` vont à img2pdf tels quels ; un JPEG est recopié à l'octet et redressé par la page ; les autres images montrent exactement les mêmes points, transparence comprise ; un GIF animé donne sa première image, un TIFF garde toutes ses pages, une photo donne une page ; un PNG 16 bits RGB ou gris garde ses données compressées telles quelles en 16 bits ; une image retournée par son EXIF (couchée, miroir) est remise à l'endroit une seule fois ; le profil de couleurs est gardé.
- **Preuve** — JPEG couché (EXIF orientation 6, profil sRGB) : le flux image de sa page égale les octets du fichier, la page porte `/Rotate 90`, le profil ICC de l'image égale celui du fichier.
- **Preuve** — PNG transparent, PNG à palette transparent, GIF animé (2 images), WebP sans perte, TIFF LZW de 2 pages (couleur puis noir et blanc), TIFF fax groupe 4 (204 x 98 dpi), TIFF couché (EXIF 6), JPEG miroir (EXIF 2) : 8 pages, chacune identique point par point à l'image attendue une fois à l'endroit (sinon c'est faux).
- **Preuve** — PNG 16 bits RGB : l'image de la page a `BitsPerComponent 16` et ses données brutes égalent le flux IDAT du fichier, sans alerte.

### F4. Photos HEIC et formats que seul macOS lit
- **Quoi** — HEIC, AVIF, RAW et tout format hors F3 sont d'abord décodés par `sips` en PNG, remis à l'endroit, puis rangés par mozjpeg en JPEG qualité 88, couleur sous-échantillonnée 4:2:0, avec leur profil de couleurs (Michael 2026-10-27 : à peu près le poids du HEIC, réglage fixe, « déterministe ») ; une image avec une vraie transparence reste en PNG sans perte ; un alpha entièrement opaque ajouté par sips est ignoré ; la conversion est refusée si elle mesure moins de 20 dB contre la photo décodée (conversion ratée) ; HDR et cartes de profondeur sont abandonnés sans alerte (Michael 2026-10-24).
- **Preuve** `[Mac]` — Avec la photo réelle de Michael `../test-HEIC/img.heic` (iPhone, couchée, Display P3) : la page est un JPEG (`/DCTDecode`), de 3024 x 4032 une fois à l'endroit, dont les moyennes des 12 blocs (3 x 4) sont à moins de 20 des valeurs de référence du self-test ; son profil a la description de `Display P3.icc` ; son flux pèse moins de 1,2 fois le HEIC.
- **Preuve** — Un HEIC fabriqué par sips à partir d'une image de bruit 4032 x 3024 donne un PDF sans alerte autre que celles que le banc ne peut éviter (date de création sous Linux).
- **Preuve** — Une image qu'aucun décodeur ne lit (fichier texte `notes.txt`) est refusée : aucun PDF, message qui nomme le fichier et finit par « Aucun PDF créé. ».

### F5. Taille des pages image
- **Quoi** — Chaque page image est affichée aussi large qu'une feuille A4 tournée dans le même sens : 21 cm pour une image portrait ou carrée, 29,7 cm pour une image paysage, et aussi haute que ses proportions, forme du point comprise (un fax 204 x 98 dpi n'est pas écrasé), quelle que soit sa résolution ; seule la taille de page change, jamais un point ; les pages PDF gardent leur taille (Michael 2026-10-25 et 2026-10-27).
- **Preuve** — Pour chaque page image des preuves F3 et F4, la boîte de page, côtés échangés si la page porte une rotation de 90 ou 270, mesure 21 cm (portrait ou carrée) ou 29,7 cm (paysage) de large à 0,01 cm près, et une hauteur égale à largeur × hauteur image / largeur image × (dpi x / dpi y) à 0,05 cm près.

### F6. Contrôle d'identité et seconde voie
- **Quoi** — Chaque page image est comparée à sa source (JPEG et PNG 16 bits à l'octet, le reste point par point, à l'endroit, même profil) ; en cas d'écart, une seconde voie décode, redresse et range les points en PNG, puis recompare ; toujours différent, ou image de plus de 8 bits que la première voie ne garde pas telle quelle : refus.
- **Preuve** — PNG 16 bits avec transparence : aucun PDF, message contenant « 8 bits » et « Aucun PDF ».
- **Preuve** — Un TIFF que Pillow lit à une taille différente de celle qu'annonce le fichier (TIFF non compressé couché) n'est jamais inséré rayé : soit la page est identique point par point à l'image à l'endroit, soit le fichier est refusé avec un message qui le nomme.
> à vérifier — la seconde preuve vient du commit `adbcca8` (« refuse a turned uncompressed TIFF that Pillow misreads ») ; le cas exact se reproduit avec Pillow 13.0.0.

### F7. Refus : rien n'est créé, le message nomme le fichier
- **Quoi** — Un fichier refusé (illisible, PDF protégé par mot de passe, dossier sélectionné, dossier non inscriptible) arrête tout : aucun PDF, un message qui nomme le fichier ou le dossier, « Aucun PDF créé. ».
- **Preuve** — `a.pdf` + `notes.txt` : aucun fichier nouveau, le message contient « notes.txt » et « Aucun PDF ».
- **Preuve** — PDF chiffré par mot de passe : aucun fichier nouveau, message contenant « mot de passe ».
- **Preuve** — Un dossier sélectionné : aucun fichier nouveau, message contenant « dossier ».
- **Preuve** — Une image dans un dossier en lecture seule (0555) : le dossier ne contient toujours que l'image, message contenant « Impossible d'écrire ».

### F8. Alertes quand le résultat perd quelque chose
- **Quoi** — Le PDF est créé, puis une seule alerte le nomme et liste, dans cet ordre : les notes graves (pièces jointes, calques, signature électronique, chacune avec « garde l'original » ; fichier réparé par qpdf, nommé) ; puis une ligne par élément de document perdu (signets, titre, auteur, sujet ou mots-clés, métadonnées XMP, balisage d'accessibilité, langue du document, liens internes nommés), chaque ligne nommant trois fichiers au plus et comptant le reste (« et N autres ») (Michael 2026-10-27). `/PageLayout`, `/PageMode` et `/ViewerPreferences` partent sans alerte. Un avertissement qpdf qui ne porte que sur des cases d'index vides (« object has offset 0 », écrit par macOS) qu'aucune référence `N G R` du fichier brut ni de ses flux d'objets ne vise ne donne pas d'alerte (Michael 2026-10-25), quelle que soit la suite de la phrase de qpdf 12 (2026-10-26).
- **Preuve** — PDF avec pièce jointe, calques et signature remplie : un PDF créé, l'alerte contient « pièces jointes », « calques », « signature » et « garde l'original ».
- **Preuve** — PDF avec signets, titre, auteur, XMP, `/StructTreeRoot`, `/Lang` et `/Names /Dests` : un PDF créé, l'alerte contient « signets », « titre », « auteur », « XMP », « accessibilité », « langue », « liens internes ».
- **Preuve** — Trois PDF titrés, un PDF à calques, deux PDF titrés : la ligne « calques » précède la ligne « titre non repris », une seule ligne commence par « titre non repris », elle contient « et 2 autres ».
- **Preuve** — PDF dont la table d'index est cassée (`startxref` faux) : PDF créé, alerte contenant « « abime.pdf » était abîmé ».
- **Preuve** — PDF de type macOS (taille de page sur l'arbre des pages) avec une case d'index vide que rien n'utilise : PDF créé, aucune ligne « abîmé » ; même PDF où la case vide est celle du contenu de la page : alerte « « vide.pdf » était abîmé ».

### F9. Dates reprises des sources
- **Quoi** — Date de création = la plus ancienne parmi création Finder, date de prise de vue (EXIF DateTimeOriginal avec son décalage) et `CreationDate` interne d'un PDF ; date de modification = la plus ancienne parmi modification Finder et `ModDate` interne d'un PDF ; dates PDF avant 1993 et prises de vue avant 1900 ignorées ; les deux écrites sur le fichier (modification d'abord) et dans `/Info` ; relues ensuite, avec une alerte si l'une n'a pas pu être recalée ; dates illisibles par exiftool : alerte.
- **Preuve** `[Mac]` — Mélange de F1 où `photo.jpg` porte une prise de vue `2019:05:12 14:03:22 +02:00` : date de création du fichier créé = 2019-05-12T14:03:22+02:00.
- **Preuve** — Même mélange où `b.pdf` porte `ModDate D:20180704120000Z` : date de modification du fichier créé = 2018-07-04T12:00:00Z, et `/Info /CreationDate` et `/ModDate` commencent par ces deux dates en heure locale.
- **Preuve** — Un PDF dont la `CreationDate` interne est en 1980 ne fait pas reculer la date de création retenue.
> à vérifier — la troisième preuve est déduite de la règle « avant 1993 ignorée » ; aucun test ne la couvre encore.

### F10. Outils manquants
- **Quoi** — Si qpdf, img2pdf, exiftool ou mozjpeg (`/opt/homebrew/opt/mozjpeg/bin/cjpeg`, keg-only) manque, l'action affiche « X est introuvable. Dans le Terminal : brew install X » et « Aucun PDF créé. », et ne crée rien.
- **Preuve** — Avec un des quatre chemins absent (banc où l'outil est retiré), l'action ne crée aucun fichier et son dialogue nomme cet outil et `brew install`.
> à vérifier — preuve déduite du code (`document.wflow`, lignes 11 à 19) ; non testée jusqu'ici.

### F11. Self-test de Créer un PDF
- **Quoi** — `test-creer-pdf.sh` lance le vrai script de l'action (extrait du `document.wflow`) avec le PATH nu du Finder, sur des fichiers jetables, journalise les dialogues au lieu de les montrer, affiche en première ligne les versions (img2pdf, pikepdf, Pillow, Python), une ligne `OK` ou `ÉCHEC` par contrôle et un bilan ; il ne touche rien hors de son dossier temporaire.
- **Preuve** — Sur le banc, sa première ligne commence par `INFO   img2pdf` et contient les quatre versions ; sa dernière ligne est `Bilan : N OK, M ÉCHEC` ; son dossier temporaire n'existe plus après la fin.
- **Preuve** — Si l'action est cassée volontairement (par exemple la qualité mozjpeg passée de 88 à 10, ou une page PDF recompressée), au moins une ligne `ÉCHEC` apparaît.
> à vérifier — le code de sortie du self-test vaut aujourd'hui 0 même avec des `ÉCHEC` ; `maj`, hors de ce dépôt, juge un passage propre sur sa sortie. Aucune preuve ici ne s'appuie sur ce code de sortie.

### F12. Rotation gauche et Rotation droite
- **Quoi** — Deux actions qui lancent le même `rotation-pdf.sh` avec `ROTATE_ANGLE` à `-90` (gauche) ou `+90` (droite) par `$HOME/Developer/scripts/services/` (Michael 2026-10-20). Chaque PDF sélectionné, ou chaque PDF au premier niveau d'un dossier sélectionné, est tourné en place : son contenu est réécrit à l'intérieur du même fichier, qui garde son inode, sa date de création et sa date de modification ; un même fichier atteint deux fois (deux chemins, dossier et PDF qu'il contient, lien) n'est tourné qu'une fois ; un verrou `<fichier>.rotation-pdf-lock` sert de garde contre deux rotations simultanées ; un fichier ou dossier en lecture seule, un PDF que qpdf doit réparer (code 3) ou qui échoue est laissé intact et compté en échec ; un bilan s'affiche sauf pour un seul succès ; le script sort en 1 s'il y a un échec.
- **Preuve** — PDF d'une page de 200 x 100 : après Rotation droite sa page porte `/Rotate 90`, après Rotation gauche sur l'original `/Rotate 270` ; son inode et sa date de modification sont inchangés.
- **Preuve** — Sélection d'un dossier contenant `x.pdf` et du même `x.pdf` : `x.pdf` porte `/Rotate 90` (pas 180).
- **Preuve** — PDF en lecture seule : octets inchangés, code de sortie 1, bilan contenant « lecture seule ».
- **Preuve** — PDF à l'index cassé : octets inchangés, code de sortie 1, bilan contenant « corrompu ».
- **Preuve** — Verrou déjà présent à côté du PDF : octets inchangés, bilan contenant « une autre rotation ».
- **Preuve** — Après tout passage, aucun dossier `*.rotation-pdf-lock` ne reste, sauf quand la remise en état a échoué.
- **Preuve** — Les deux `document.wflow` passent `ROTATE_ANGLE` à `-90` (gauche) et `+90` (droite) et appellent `$HOME/Developer/scripts/services/rotation-pdf.sh`.
- **Preuve** `[Mac]` — Date de création inchangée après rotation.

### F13. Éditer les métadonnées (connecteur metmux)
- **Quoi** — Lance dans Terminal `metmux.py --mode=ask` suivi des chemins sélectionnés, avec le premier Python trouvé parmi `/opt/homebrew/bin/python3`, `/usr/local/bin/python3`, `python3`, `python` ; la commande passe à osascript en argument, jamais dans le texte AppleScript ; metmux absent ou Python absent : dialogue « metmux » et sortie 1. Le dépôt metmux n'est que lu (Michael 2026-10-19). Le workflow n'a pas d'icône (aucune clé `NSIconName`/`NSBackgroundColorName` dans `Info.plist`, aucune `systemImageName`/`backgroundColorName` dans `document.wflow`) (Michael 2026-10-19).
- **Preuve** — Avec un faux `metmux.py` au chemin attendu et osascript doublé qui écrit ses arguments, des chemins contenant espace, apostrophe, guillemet et accent produisent une commande qui, rejouée par bash, passe à metmux exactement ces chemins, précédés de `--mode=ask`.
- **Preuve** — Sans `metmux.py` : code de sortie 1, dialogue contenant « metmux.py est introuvable ».
- **Preuve** — `grep` des quatre clés d'icône dans les deux plists du workflow : aucune occurrence.

### F14. OCR sur PDF (connecteur ocrswap)
- **Quoi** — Une seule fenêtre Terminal pour toute la sélection : `printf` d'effacement, puis `/Users/michael/Developer/ocrswap/.venv/bin/python3 /Users/michael/Developer/ocrswap/ocrswap.py` suivi de tous les chemins ; sans sélection, rien. Le dépôt ocrswap n'est que lu (Michael 2026-10-20).
- **Preuve** — Avec trois chemins (dont un avec apostrophe, guillemet et barre oblique inverse) et osascript doublé, exactement un appel `do script`, dont la commande, une fois déséchappée d'AppleScript et rejouée par bash, passe à ocrswap exactement ces trois chemins dans l'ordre.
- **Preuve** — Sans argument : aucun appel à osascript, sortie 0.

### F15. `sync.sh`
- **Quoi** — Relie chaque `*.workflow` du dépôt dans `~/Library/Services` sous le même nom, par lien symbolique ; ne change aucun lien quand tout est déjà relié ; retire un lien vers le dossier scripts dont la cible n'existe plus ; retire une copie réelle dont chaque fichier est déjà connu de git (de ce dépôt ou du dépôt scripts) ; remplace un lien homonyme qui pointe ailleurs ; laisse et signale une copie réelle homonyme que git ne connaît pas ; installe par brew l'outil manquant parmi qpdf, img2pdf, exiftool, mozjpeg ; sort en 1 s'il reste un problème (Michael 2026-10-20).
- **Preuve** — `HOME` jetable, `~/Library/Services` vide : après un passage, un lien par workflow, chacun pointant vers le dossier du dépôt ; un second passage ne modifie aucun lien (mêmes inodes, aucune ligne « relié »).
- **Preuve** — Lien `Vieux.workflow` vers un chemin absent sous le dossier scripts : retiré. Copie réelle d'un workflow identique au dépôt : retirée puis remplacée par un lien. Copie réelle homonyme modifiée : gardée intacte, message sur stderr, code 1. Lien homonyme vers ailleurs : remplacé.
- **Preuve** — Outil manquant et brew absent : message « manque et n'a pas pu être installé », code 1.

### F16. Menus du Finder
- **Quoi** — Chaque action se déclare au Finder avec son nom et ses types de fichiers : Créer un PDF (PDF, images), OCR sur PDF (PDF, dossiers), Rotation droite (PDF, dossiers), Rotation gauche (tout élément), Éditer les métadonnées (tout élément). Aucun fichier du dépôt ne porte d'en-tête `# menu:` (le lanceur ne doit jamais lister ce dossier).
- **Preuve** — Lecture des cinq `Info.plist` : le `NSMenuItem` et les `NSSendFileTypes` valent ceux de la liste ci-dessus.
- **Preuve** — `grep -r '# menu:'` dans le dépôt : aucune occurrence.
> à vérifier — Rotation gauche accepte « tout élément » (`public.item`) et porte une icône, alors que Rotation droite accepte PDF et dossiers sans icône. Gardé tel quel (décidé par dev en l'absence du PO, à revoir) : voir `BARRE.md`, section 4.

## 3. Interdictions & limites + preuves

- **Originaux de Créer un PDF jamais touchés** — preuve : empreinte sha256 et date de modification de chaque fichier sélectionné identiques avant et après l'action, dans chaque scénario de F1 à F8.
- **Jamais un point d'image changé, hors photos que seul macOS lit (F4)** — preuve : les comparaisons point par point ou à l'octet de F3 et F6.
- **Un refus ne crée rien** — preuve : dans chaque scénario de F7, la liste du dossier est la même avant et après.
- **Les dépôts metmux et ocrswap ne sont jamais modifiés, le workflow publié par metmux et l'action publiée par ocrswap ne sont jamais utilisés** — preuve : les deux `document.wflow` ne contiennent aucune écriture vers `/Users/michael/Developer/metmux` ni `/Users/michael/Developer/ocrswap` (aucune redirection, `cp`, `mv`, `rm`, `git` vers ces chemins), et l'exécution de F13 et F14 laisse les faux dépôts identiques octet pour octet ; `local/regen_quickaction.py` n'est appelé nulle part.
- **pikepdf : seulement des appels présents depuis 10.0, jamais `Page.get_images`** (le Mac peut avoir un pikepdf en retard) — preuve : aucune occurrence de `get_images` dans le dépôt ; le self-test donne le même bilan avec pikepdf 10.5.1 (Python 3.14) et pikepdf 10.16.0 (Python 3.15).
> à vérifier — la version 10.0.0 elle-même n'est pas exercée : la preuve couvre les deux versions que le `CLAUDE.md` nomme pour le Mac et pour la prochaine bouteille Homebrew.
- **Outils appelés par chemin absolu Homebrew** (`/opt/homebrew/bin/…`, mozjpeg par `/opt/homebrew/opt/mozjpeg/bin/cjpeg`), car une action rapide n'hérite pas du PATH du Terminal — preuve : le self-test lance l'action avec `PATH=…:/usr/bin:/bin:/usr/sbin:/sbin` sans `/opt/homebrew` et réussit.
- **Rotation : jamais de remplacement du fichier (`--replace-input` interdit)** — preuve : inode identique avant et après rotation (F12) ; aucune occurrence de `replace-input` dans le code exécuté.
- **Rotation : bash 3.2 de macOS** — preuve : aucun tableau vide développé sous `set -u` (le script passe sur un dossier sans PDF sans erreur) ; `[Mac]` le script tourne avec `/bin/bash` 3.2.
- **Aucun secret, rien publié, rien poussé sur `main`** — preuve : `git log main..` ne contient aucun commit sur `main` fait par ce cycle ; aucun jeton dans le diff.

## 4. Risques d'interaction + preuves

- **Self-test ↔ action Créer un PDF** — le self-test exerce le script tel qu'il est dans `document.wflow`, jamais une copie : preuve, modifier une ligne du script dans `document.wflow` (F11, mutation) change le bilan.
- **`sync.sh` ↔ toutes les actions** — un `Info.plist` modifié n'apparaît qu'après un passage de `sync.sh` (`pbs -flush`) ; un double-clic sur un `.workflow` dans le Finder le déplace dans `~/Library/Services` et transforme le lien en copie figée (Michael 2026-10-20) : preuve, F15 retire une copie réelle identique au dépôt et la remplace par un lien.
- **Rotation ↔ emplacement du dossier scripts** — les deux rotations atteignent `rotation-pdf.sh` par `$HOME/Developer/scripts/services/` : preuve, F12 (lecture des deux `document.wflow`). Déplacer le dossier impose de modifier les deux.
- **Créer un PDF ↔ dates** — la modification s'écrit avant la création, car abaisser la modification sous la création entraîne la création avec elle : preuve `[Mac]`, F9 (création et modification retrouvées toutes deux).
- **Créer un PDF lancé deux fois en même temps** — la création exclusive du nom réserve le nom : preuve, deux lancements simultanés sur `b.pdf` donnent deux fichiers de noms différents (`b 2.pdf`, `b 3.pdf`), jamais un fichier écrasé.
> à vérifier — preuve déduite du code (ouverture `xb`) ; non testée jusqu'ici.

## 5. Tests de robustesse

- **Noms exotiques** : chemins avec espace, apostrophe, guillemet, accent, barre oblique inverse, dans Créer un PDF (le PDF créé porte le nom attendu), Rotation (le fichier est tourné) et les deux connecteurs (F13, F14).
- **Erreur inattendue jamais muette** : si une bibliothèque lève une exception imprévue, Créer un PDF affiche « erreur inattendue (Type : message) » et, si un PDF a déjà été écrit, le nomme.
- **Dossier de travail nettoyé** : après chaque lancement de Créer un PDF, le dossier temporaire créé par l'action n'existe plus.
- **Banc vert sans faux vert** : chaque test d'une preuve échoue si l'on casse le comportement qu'elle décrit (vérifié par au moins une mutation volontaire par fonctionnalité testée dans la VM).

## 6. Livrables attendus

- Les cinq actions (`*.workflow`), `rotation-pdf.sh`, `sync.sh`, `test-creer-pdf.sh`, tels que le Mac les relie par `sync.sh`.
- Les tests qui couvrent les preuves rejouables dans la VM, lançables par une seule commande, avec un code de sortie non nul au premier échec ; les preuves `[Mac]` listées à part, avec la commande que Michael lance sur son Mac.
- `CLAUDE.md` à jour de tout fait durable appris pendant le cycle.

## 7. Ce que je fournis

- **Greffe sur l'existant** (recherche d'existant du 2026-11-05) : aucun outil maintenu ne fait ensemble l'assemblage sans perte avec contrôle d'identité, la reprise des dates et les alertes, ni la rotation en place qui garde l'inode ; le projet se greffe déjà sur les briques maintenues qpdf, img2pdf, Pillow, pikepdf, exiftool, mozjpeg et `sips`, et le « Créer un PDF » natif du Finder donne la référence pour l'ordre des clics et le nom. Le delta construit ici est le reste (F1 à F16).
> à vérifier — recherche faite par extraits : support.apple.com et formulae.brew.sh ne se lisent pas depuis la VM ; le comportement réel du « Créer un PDF » natif (recompression, dates) n'est établi par aucune page Apple.

- **Corpus protégé** : la photo réelle `test-HEIC/img.heic`, dans le dossier parent du dépôt sur le Mac (`~/Developer/scripts/test-HEIC/img.heic`), hors de ce dépôt ; à ne jamais supprimer ni remplacer (Michael 2026-10-27). Elle n'est pas dans la VM : les preuves qui en dépendent sont `[Mac]`.
> à vérifier — chemin déduit de `test-creer-pdf.sh` (`../test-HEIC/img.heic` relatif au dossier du script).
