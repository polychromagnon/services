# BARRE — services (actions Finder de Michael)

> **Le principe.** Ce fichier est le tien : c'est le seul que tu dois ouvrir. Tout ce qui attend un geste de ta part est ici, et rien d'autre. L'équipage (`/dev` : spec, ship, send) le lit avant chaque run, le tient à jour, et n'efface jamais une ligne que tu as écrite.
>
> **Le partage des rôles.** `SPEC.md` est le contrat technique, tenu pour l'équipage : tu peux le lire, tu n'as jamais à y intervenir. Ici, chaque section dit qui écrit et ce que ta réponse déclenche.

---

## 1. Gravé dans le marbre — tes volontés

> Tes décisions durables, une par ligne, numérotées à la suite. L'équipage les applique à chaque cycle sans les rediscuter. Un **NON** écrit ici est définitif : l'objet refusé ne te sera jamais reproposé (ses voisins restent permis). Pour changer d'avis, édite ou retire la ligne : le prochain run s'aligne. Une nouvelle volonté s'ajoute en fin de liste, sans renuméroter.

- (vide : aucune volonté gravée ici à ce jour ; tes décisions datées vivent dans `CLAUDE.md`, et le SPEC les reprend)

## 2. Politiques en ton absence (`/dev auto`)

> Tes réponses données d'avance aux questions qui surgiraient pendant un run sans toi. Pour tout ce qui n'a pas de ligne ici, l'équipage prend le défaut le plus sûr et le consigne en section 4.

- features : SANS (MVP strict)
- parallele : OFF
- doute de périmètre : option minimale et réversible
- enjeu : … (+, ++ ou +++ ; prime sur le ++ par défaut ; vide, ++ s'applique quand tu lances toi-même en session, et une chasse sans toi n'attaque rien, sauf niveau fixé par le métier qui la lance ; ++++ ne se lit jamais ici)

## 3. ⚠ À TRANCHER — l'équipage attend ta décision

> Une décision par ligne : qui la pose, la question, la proposition de l'équipage, puis la flèche où tu réponds (un mot suffit : oui, non, un chiffre, un choix). Le prochain run lit ta réponse, l'applique, retire la ligne, et grave en section 1 ce qui mérite de durer. **Section vide : rien ne t'attend.** Tant qu'une ligne reste sans réponse, le SPEC n'est pas figé et rien ne part en production.

- [ship, relecture du code] Rotation interrompue brutalement (coupure, arrêt forcé) : le PDF peut rester coupé mais s'ouvrir quand même, pages vides ou manquantes. Le message te dit de remettre la copie de sécurité « si le PDF ne s'ouvre pas normalement », et j'ai ajouté « dans le doute, remettez la copie ». Faut-il dire de remettre la copie dans tous les cas ? Proposition : oui, au pire la rotation est annulée, jamais l'original perdu. →
- [ship, relecture du code] Noms de fichier très longs (plus de 236 caractères environ) : la rotation refuse avec un message faux (« une autre rotation semble déjà en cours »), et Créer un PDF refuse avec « Impossible d'écrire » quand le nom final dépasse la limite ; aucun fichier n'est abîmé. Faut-il un message juste (« nom trop long, raccourcis-le ») ? Proposition : oui. →
- [ship, relecture du code] Rotation d'un PDF signé électroniquement : la signature ne vaut plus après rotation, sans alerte, alors que Créer un PDF t'alerte dans ce cas. Faut-il refuser la rotation avec « signé : garde l'original » ? Proposition : oui (déjà au backlog). →
- [ship, relecture du code] Après un arrêt forcé de Créer un PDF, un fichier « … (PDF en cours N) » reste dans le dossier, sans que rien ne te le signale. Faut-il qu'un lancement suivant le signale (sans le supprimer) ? Proposition : oui. →
- [ship, relecture du code] Très gros lots (scans TIFF de centaines de pages) : aucun budget de temps ni de mémoire n'est fixé ni testé. Faut-il en fixer un ? Proposition : non, tu le diras si un cas te gêne. →
- [ship, relecture du code] La preuve iCloud de `preuves-mac.sh` vérifie maintenant que ton dossier Documents est synchronisé, et sinon dit « preuve non exercée » au lieu d'un faux OK. Ça te va ? Proposition : oui. →

## 4. Décidé sans toi — à revoir

> Une ligne par décision prise en ton absence : le choix, l'alternative écartée, la raison. Trois gestes possibles : tu la laisses (elle reste un défaut tacite), tu la graves en section 1 (elle devient loi), ou tu écris **NON** en fin de ligne (le prochain run la défait et repose la question en section 3).

- [spec 2026-11-05] Politiques : aucune n'était écrite ; défauts appliqués (features SANS, parallèle OFF, doute de périmètre : option minimale et réversible) ; enjeu +++ pris dans ta commande `/dev auto +++`.
- [spec 2026-11-05] But du cycle : figer et prouver le comportement actuel que `CLAUDE.md` décrit, sans fonctionnalité nouvelle. Écarté : inventer un besoin. Raison : aucun besoin n'était écrit, et c'est l'option minimale et réversible.
- [spec 2026-11-05] Rotation gauche reste telle quelle : tout élément (`public.item`) et une icône, alors que Rotation droite prend PDF et dossiers sans icône. Écarté : la rendre symétrique de Rotation droite (proposition de la relecture). Raison : c'est ton menu, la changer sans toi n'est pas réversible à tes yeux tant que tu ne l'as pas vu ; dis « symétrique » pour l'aligner.
- [spec 2026-11-05] Le self-test de ton Mac garde exactement ses contrôles, sa sortie (`INFO` en première ligne, `Bilan : N OK, M ÉCHEC` en dernière) et son code de sortie (0 même avec des ÉCHEC) ; les preuves sont portées par une suite de tests séparée qui tourne dans la VM. Écarté : ajouter des lignes au self-test ou le faire sortir en 1. Raison : `maj`, hors de ce dépôt, lit cette sortie et te notifie ; je ne peux pas voir comment, donc je n'y touche pas.
- [spec 2026-11-05] Rotation : la preuve « bash 3.2 de macOS » reste une lecture du script dans la VM plus un geste sur ton Mac. Écarté : compiler le bash 3.2 d'Apple dans la VM. Raison : le contrôle automatique des permissions de la session l'a refusé (code externe).
- [spec 2026-11-05] Rotation interrompue pendant la réécriture (fermeture de session, arrêt de l'action) : le code actuel laisse le PDF tronqué et efface sa copie de sécurité ; ship le corrige dans ce cycle pour qu'il reste l'original ou la copie de sécurité. Écarté : seulement le signaler. Raison : ton principe « jamais de perte » et celui écrit dans le script lui-même ; ce n'est pas une fonctionnalité nouvelle.
- [spec 2026-11-05] `sync.sh` après un double-clic sur un `.workflow` : il retire la copie déplacée dans `~/Library/Services` (git la garde) et l'action n'est plus installée jusqu'à `git restore` ; gardé tel quel, c'est ta règle du 2026-10-20. Écarté : refuser de retirer une copie dont la source manque au dépôt (mis au backlog). Raison : changer ta règle sans toi.
- [spec 2026-11-05] Rotation d'un PDF de macOS (scan, Aperçu) dont qpdf signale des cases d'index vides : la rotation le refuse aujourd'hui comme « corrompu » (fichier intact), alors que Créer un PDF l'accepte sans alerte depuis ta décision du 2026-10-25 ; gardé tel quel, mis au backlog. Écarté : étendre ta règle à la rotation. Raison : c'est une règle de produit, et le refus ne perd rien.
- [spec 2026-11-05] Rotation : les flux du PDF sont réécrits décompressés (`--compress-streams=n`), le fichier peut beaucoup grossir (2,7 Ko → 340 Ko mesuré sur un PDF de texte), sans perte ; gardé tel quel, mis au backlog. Écarté : recopier les flux tels quels comme Créer un PDF. Raison : je ne sais pas si c'était voulu.
- [spec 2026-11-05] Rotation : quand le dossier de verrou garde la seule copie intacte, le message ne dira plus « supprimez le dossier » mais nommera la copie ; ship le corrige. Raison : sans perte.
- [spec 2026-11-05] Créer un PDF : une image couchée par son EXIF et à points non carrés (fax, certains scans) sort étirée quand elle passe par la seconde voie (fax 60 x 40 couché : 21 x 65,6 cm au lieu de 29,7 x 21,4 cm) ; ship le corrige dans ce cycle. Raison : ta décision du 2026-10-25, « un fax n'est pas écrasé ».
- [spec 2026-11-05] `sync.sh` ne touchera plus jamais aux trois actions `Claude - ask/codeHere/send`, même si git connaît leurs fichiers (aujourd'hui il pourrait les retirer comme doublons) ; ship le corrige. Écarté : seulement reformuler la promesse. Raison : ta règle « elles appartiennent à l'app Claude et restent hors », et c'est l'option sûre et réversible.
- [spec 2026-11-05] Rotation : la remise à l'identique rétablira aussi la date de création (aujourd'hui seulement la modification), et la copie de sécurité sera écrite sous un nom provisoire puis renommée une fois complète (aujourd'hui un arrêt brutal pendant la copie laisse une copie tronquée sous son vrai nom) ; ship les corrige. Raison : sans perte.
- [spec 2026-11-05] Créer un PDF : un JPEG tronqué (photo coupée par un transfert) passe tel quel, sans alerte, comme aujourd'hui ; les autres formats tronqués sont refusés. Écartés : refuser aussi le JPEG, ou créer le PDF avec une ligne « semble coupé » dans l'alerte (les deux au backlog). Raison : le PDF garde exactement les octets de la source, rien n'est perdu par rapport à elle ; refuser serait une règle nouvelle.
- [spec 2026-11-05] Le SPEC ne fige plus le texte exact de chaque mutation de test : il fixe la règle (chaque sous-fait a une mutation qui le fait échouer), ship choisit et prouve. Écarté : corriger la liste une quatrième fois. Raison : elle est revenue en défaut à trois relectures (soupape de trust).
- [spec 2026-11-05] Les preuves qui ne tournent que sur ton Mac seront livrées en un script, `preuves-mac.sh`, à lancer en une commande ; seuls l'ordre des clics et la place dans le menu restent des gestes à la main. Raison : sinon personne ne les rejouerait.
- [spec 2026-11-05] OUVERT, pour le prochain cycle (soupape de trust : la même cause est revenue trois fois et plus) : la protection de la rotation contre les interruptions. Ce cycle corrige un signal pendant la réécriture et l'arrêt brutal. Restent sans preuve : une seconde interruption pendant la remise depuis la copie (deux Ctrl-C, fermeture de session), et un lot de PDF arrêté au milieu (les PDF déjà tournés ne sont pas nommés ; relancer la même sélection les tournerait une seconde fois). Écris « oui » en fin de ligne pour les mettre au prochain cycle.
- [spec 2026-11-05] Créer un PDF arrêté pendant l'écriture du résultat (fermeture de session, arrêt forcé) : aujourd'hui un PDF tronqué ou vide reste sous un nom normal, sans message ; ship le corrige (écriture complète sous un nom provisoire qui ne finit pas par `.pdf`, puis nom final par lien dur exclusif). Limite : sur une clé exFAT ou un partage réseau sans liens durs, l'écriture d'aujourd'hui reste. Raison : tu supprimes tes originaux après la fusion.
- [spec 2026-11-05] Rotation : quand un verrou orphelin garde la copie, le message te dira d'abord « si le PDF ne s'ouvre pas normalement, remets `copie-de-securite.pdf` à sa place », puis seulement de supprimer le dossier.
- [ship 2026-11-05] Un TIFF orienté sur sa diagonale (EXIF 5 à 8) passe directement par la seconde voie, sans perte (PNG) : Pillow le donne déjà tourné à img2pdf mais avec sa densité d'origine, la page sortait étirée. Écarté : corriger la taille calculée par img2pdf. Raison : la seconde voie, déjà prouvée, suffit.
- [ship 2026-11-05] Le fichier provisoire de Créer un PDF s'appelle « <nom> (PDF en cours <numéro>) », raccourci si besoin pour tenir dans 255 octets. Raison : lisible si un arrêt brutal le laisse, jamais pris par une rotation de dossier.
- [ship 2026-11-05] Le message de verrou ajoute « dans le doute, remettez la copie (au pire, la rotation est annulée) », sans sortir du texte que le SPEC impose ; la question d'une remise systématique t'est posée en section 3.
- [ship 2026-11-05] Liste des mutations ajustée là où le texte indicatif du SPEC ne mordait pas ou n'existait plus (41 au total, toutes attrapées) ; le harnais tourne avec VERIFY_RELAX=1 sur une copie de l'arbre (commande dans CLAUDE.md).
- [ship 2026-11-05] Relecture du code arrêtée après sa première attaque : elle a relevé des lacunes du SPEC, et ta règle en ton absence dit de figer et de te les poser (section 3). Ses quatre points forts sont réparés, sans nouvelle attaque.

## 5. État du chantier

> Écrit par le dernier run, verdict en première ligne. Le détail des preuves vit dans `dossier/proof.md` ; ici, seulement ce qui t'oriente.

**Verdict : bloqué, ship : lacunes du SPEC, PO requis** — intention non validée par un humain, essaie le produit pour vérifier qu'il fait ce que tu voulais. Relecture du SPEC : plafond de 12 attaques atteint sans converger. Relecture du code : une seule attaque, puis gel sur lacunes ; le code a changé après elle (réparations de ses quatre points forts).

- Fait : sept défauts corrigés (fax ou image couchée étirés, PDF partiel laissé par un arrêt, rotation interrompue qui perdait l'original, message de verrou, date de création après remise, copie de sécurité tronquée sous son vrai nom, actions Claude exposées à `sync.sh`) ; suite de tests VM (232 contrôles, tous verts, aussi sous pikepdf 10.0.0 et 10.16.0) ; 41 mutations toutes attrapées ; `preuves-mac.sh` ; preuve d'exécution dans `proof.lock`, détail dans `proof.md`.
- Reste : réponds aux six questions de la section 3 ; lance `bash ~/Developer/scripts/services/preuves-mac.sh` sur ton Mac et renvoie ce qu'il affiche ; puis relance `/dev`.
- Bloqué : la release (send) attend tes réponses.
- En attente de ton feu vert : fusion de la branche `claude/wizardly-faraday-hk83yo` dans `main` (rien n'a été poussé sur `main`).
