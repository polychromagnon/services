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


## 4. Décidé sans toi — à revoir

> Une ligne par décision prise en ton absence : le choix, l'alternative écartée, la raison. Trois gestes possibles : tu la laisses (elle reste un défaut tacite), tu la graves en section 1 (elle devient loi), ou tu écris **NON** en fin de ligne (le prochain run la défait et repose la question en section 3).

- [spec 2026-11-05] Politiques : aucune n'était écrite ; défauts appliqués (features SANS, parallèle OFF, doute de périmètre : option minimale et réversible) ; enjeu +++ pris dans ta commande `/dev auto +++`.
- [spec 2026-11-05] But du cycle : figer et prouver le comportement actuel que `CLAUDE.md` décrit, sans fonctionnalité nouvelle. Écarté : inventer un besoin. Raison : aucun besoin n'était écrit, et c'est l'option minimale et réversible.
- [spec 2026-11-05] Rotation gauche reste telle quelle : tout élément (`public.item`) et une icône, alors que Rotation droite prend PDF et dossiers sans icône. Écarté : la rendre symétrique de Rotation droite (proposition de la relecture). Raison : c'est ton menu, la changer sans toi n'est pas réversible à tes yeux tant que tu ne l'as pas vu ; dis « symétrique » pour l'aligner.
- [spec 2026-11-05] Le self-test garde son code de sortie d'aujourd'hui (0 même avec des ÉCHEC) et sa grammaire (`INFO` en première ligne, `Bilan : N OK, M ÉCHEC` en dernière) ; les tests de la VM jugent ses lignes, pas son code. Écarté : sortir en 1 sur un ÉCHEC. Raison : `maj`, hors de ce dépôt, lit cette sortie et je ne peux pas voir comment ; un code changé pourrait l'arrêter.
- [spec 2026-11-05] Dans la VM seulement, le self-test marque `SAUTÉ` la date de création et la photo réelle, et ne retire du dialogue que la ligne « la date de création du fichier n'a pas pu être recalée ». Écarté : tolérer des ÉCHEC attendus. Raison : un total d'échecs attendus cacherait une vraie alerte en plus ; sur ton Mac rien ne change.

## 5. État du chantier

> Écrit par le dernier run, verdict en première ligne. Le détail des preuves vit dans `dossier/proof.md` ; ici, seulement ce qui t'oriente.

**Verdict : —**

- Fait : …
- Reste : …
- Bloqué : …
- En attente de ton feu vert : …
