# Notes de session Pynab - 2026-05-01

Notes brutes de travail sur le fork `pynab-vifra`.

## Contexte general

- Machine de dev : Windows / PowerShell.
- Cible lapin : `pi@nabaztag.local`.
- Repertoire cible utilise sur le lapin : `/opt/pynab-vifra`.
- Venv Python reel sur le lapin : `/opt/pynab/venv/bin/python`.
- Les services systemd existants utilisent souvent `root`, pas `pynab`.
- Commandes de migration a lancer depuis `/opt/pynab-vifra` :

```bash
/opt/pynab/venv/bin/python manage.py migrate <app>
```

- Ne pas utiliser `sudo -u pynab` : l'utilisateur `pynab` n'existe pas sur ce lapin.

## Deploiement / SCP

Convention retenue : toujours utiliser `pi@nabaztag.local`, pas un alias `lapin`.

Exemples :

```bash
scp path/local/file.py pi@nabaztag.local:/opt/pynab-vifra/path/local/file.py
sudo systemctl restart nabweb.service
```

Pour un dossier :

```bash
scp -r nabsound pi@nabaztag.local:/opt/pynab-vifra/
```

Services a redemarrer selon les changements :

- Templates / views Django : `sudo systemctl restart nabweb.service`
- Planificateur : `sudo systemctl restart nabplannerd.service`
- Menu du jour : `sudo systemctl restart nabmenudujour.service`
- Tai chi : `sudo systemctl restart nabtaichid.service`
- Humeurs : `sudo systemctl restart nabsurprised.service`
- Coeur Pynab / audio : `sudo systemctl restart nabd.service`

## Git / fork

Il y a eu une alerte de push vers `nabaztag2018` au lieu du fork.

Commande utilisee pour verifier :

```bash
git branch -vv
```

Etat observe :

```text
* master 4c1af46 [origin/master] Module "Menu du jour"
```

Conclusion : verifier `git remote -v` avant push si doute.

## Module Menu du jour - `nabmenudujour`

Objectif initial :

- creer un module `nabmenudujour`;
- lire un JSON depuis une URL configuree dans l'interface web;
- annoncer le repas du jour.

URL JSON utilisee :

```text
https://script.google.com/macros/s/AKfycbyCOjaCmGKdgk_kQWTRAw29hi3e-STLcsvgfUSOPWIFn_aT3nMbJYPC1SxRxp_GBGIk9A/exec?k=menu-2026-famille-x7p9&format=json
```

Champs utiles uniquement :

- `dateLongue`
- `midi`
- `soir`

Comportement :

- web UI pour definir l'URL;
- bouton "Read now";
- support tag RFID/NFC;
- le module doit annoncer uniquement date longue + midi + soir.

Problemes rencontres :

- migration appelee avec mauvais venv :

```bash
./env/bin/python manage.py migrate nabmenudujour
```

Erreur :

```text
./env/bin/python: No such file or directory
```

Correction :

```bash
/opt/pynab/venv/bin/python manage.py migrate nabmenudujour
```

- service `nabmenudujour` bloque avec :

```text
nabmenudujour already running? (pid=...)
```

Procedure :

```bash
sudo systemctl stop nabmenudujour.service
ps -fp <pid>
sudo kill <pid>
sudo rm -f /run/nabmenudujour.pid
sudo systemctl start nabmenudujour.service
```

## RFID / NFC

Proleme initial :

- impossible de parametrer un tag NFC dans `/rfid/`;
- ensuite le tag pouvait etre associe mais ne declenchait pas le menu.

Travail fait :

- ajout support service pour `nabmenudujour`;
- correction pour que "Read now" et RFID puissent demander l'annonce du menu.

## Planificateur - `nabplannerd`

Objectif :

- nouvelle page :

```text
http://nabaztag.local/planification/
```

- definir :
  - plages horaires d'activite de services;
  - heures fixes de declenchement;
  - recurrence de declenchement.

Exemples utilisateur :

- meteo accessible de 10h a 20h, declenchements a 10h30, 14h, 19h59;
- menus annonces toutes les heures de 10h30 a 19h30.

Structure :

- module `nabplannerd`;
- model `ScheduledRule`;
- daemon systemd `nabplannerd.service`;
- interface web `/planification/`;
- entrees dans `nabweb/settings.py`, `nabweb/urls.py`, nav `_base.html`.

Modes :

- `times` : heures fixes;
- `interval` : recurrence;
- `window` : plage d'activite.

Champs principaux :

- `service`
- `action`
- `color`
- `enabled`
- `mode`
- `weekdays`
- `start_time`
- `end_time`
- `trigger_times`
- `interval_minutes`
- `last_triggered_key`

## Planificateur - systemd / daemon

Erreur initiale :

```text
django.core.exceptions.ImproperlyConfigured:
Requested setting INSTALLED_APPS, but settings are not configured.
```

Cause :

- import de models Django trop tot, avant configuration settings.

Correction :

- import du scheduler deplace dans la boucle de service, apres initialisation Django par `NabService`.

Autre probleme :

```text
nabplannerd already running? (pid=...)
```

Procedure :

```bash
sudo systemctl stop nabplannerd.service
ps -fp <pid>
sudo kill <pid>
sudo rm -f /run/nabplannerd.pid
sudo systemctl start nabplannerd.service
```

## Planificateur - fonctionnement

Ce n'est pas une crontab.

Fonctionnement :

- daemon systemd;
- boucle toutes les 30 secondes environ;
- calcule les regles dues;
- pour meteo/menu, remplit `next_performance_date` / `next_performance_type` dans la config du service cible puis signale le daemon cible.

Commande de curiosite pour lire une config service :

```bash
/opt/pynab/venv/bin/python manage.py shell -c "from nabmenudujour.models import Config; c=Config.load(); print(c.next_performance_date, c.next_performance_type)"
```

Important :

- `next_performance_date` du service cible reste `None` tant que le planificateur n'a pas declenche.
- Les prochaines dates du planificateur sont dans les regles de `nabplannerd`, pas dans les configs des services tant que l'heure n'est pas due.

## Planificateur - jours actifs

Ajout de la possibilite de definir des jours actifs :

- semaine;
- week-end;
- tous;
- selection manuelle.

Permet de differencier semaine et week-end.

## Planificateur - UI timeline

Evolution de l'interface :

- vue hebdomadaire graphique;
- 0h -> 0h, pas seulement 6h -> fin;
- affichage des cellules ou le lapin dort, d'apres le module Horloge;
- pastilles pour heures fixes;
- barres pour plages d'activite;
- couleurs par service/regle;
- texte contraste automatiquement selon la couleur de fond;
- empilement vertical des plages qui se chevauchent;
- pastilles placees au-dessus des barres.

Regles UI :

- les blocs de configuration ne sont plus tous visibles;
- clic sur une plage/pastille dans la timeline affiche uniquement la regle correspondante en edition;
- creation/edition placee a droite de la timeline;
- bouton "Nouvelle regle" dans le bloc d'edition.

Corrections UI notables :

- le champ couleur etait trop grand et faux en edition;
- il a ete deplace pres du titre;
- un seul champ `color` est envoye, via champ cache pilote par le picker visible.

## Planificateur - formulaire

Changements :

- en creation, aucun service selectionne par defaut;
- service obligatoire;
- type obligatoire;
- selon le type, afficher seulement :
  - plage : debut/fin;
  - heures fixes : heures de declenchement;
  - recurrence : toutes les N minutes + a partir de + jusqu'a.

Nettoyage serveur :

- le serveur nettoie les champs non pertinents selon le mode choisi.

## Planificateur - recurrence

Ajouts :

- champ "A partir de";
- champ "Jusqu'a";
- generation de pastilles pour occurrences recurrentes quand le nombre reste lisible;
- sinon, fallback sur barre avec marqueurs.

Pour recurrence :

- `start_time` = a partir de;
- `end_time` = jusqu'a;
- `interval_minutes` = pas de recurrence.

## Planificateur - titre des pastilles

Demande :

- title de pastille = `<nom du service> - <heure prevue>`.

Implementation :

- separation `service_name` du label complet.

## Planificateur - services supportes

Services :

- `nabweatherd` : meteo;
- `nabmenudujour` : menu du jour;
- `nabtaichid` : tai chi;
- `nabsurprised` : humeurs.

Actions :

- meteo : `today`, `tomorrow`;
- menu : `today`;
- tai chi : `active_window`;
- humeurs : `active_window`.

## Tai chi

Demande :

- le module tai chi gere deja sa recurrence;
- le planificateur doit seulement definir des plages d'activite.

Implementation :

- pour `nabtaichid`, forcer `mode=window` et `action=active_window`;
- masquer type/action inutiles;
- le daemon tai chi doit consulter les plages du planificateur pour choisir sa prochaine occurrence.

## Humeurs

Demande :

- de la meme maniere que tai chi, planifier les humeurs du jour.

Implementation :

- ajout service `nabsurprised`;
- plages d'activite uniquement;
- `mode=window`, `action=active_window`;
- le daemon humeurs consulte les plages du planificateur.

## Couleurs par service planifie

Ajout :

- chaque regle a une couleur;
- couleur visible dans :
  - pastilles;
  - plages;
  - bloc de configuration.

Couleurs par defaut :

- meteo : `#2077b4`
- menu : `#27865a`
- tai chi : `#b45f06`
- humeurs : `#c2185b`
- disabled : `#adb5bd`

## Contraste texte timeline

Ajout :

- calcul automatique d'une couleur de texte noire ou blanche selon la luminance du fond.

Fonction logique :

- si fond clair, texte sombre;
- sinon texte blanc.

## Planificateur - declenchements rates

Cas rencontre :

- regle menu/meteo programmee mais rien ne se lance.

Diagnostics :

```bash
systemctl status nabplannerd.service --no-pager
journalctl -u nabplannerd.service --since "2026-05-01 18:30:00" --no-pager
```

Sur certains systemes :

```bash
journalctl --since "today 18:30"
```

ne marche pas. Utiliser date complete.

Diagnostic due :

```bash
cd /opt/pynab-vifra
/opt/pynab/venv/bin/python manage.py shell -c "import datetime; from nabplannerd.models import ScheduledRule; from nabplannerd.scheduler import due_trigger_key; d=datetime.date.today(); now=datetime.datetime.combine(d, datetime.time(18,35)); print('simulated', now, now.weekday()); [print(r.id, r.service, r.mode, r.weekdays, r.trigger_times, r.last_triggered_key, 'due=', due_trigger_key(r, now)) for r in ScheduledRule.objects.filter(enabled=True)]"
```

Probleme trouve :

- `nabplannerd` etait bloque avec `already running?`.

Autre correction :

- les regles `times` ne doivent pas etre bloquees par `start_time/end_time`;
- `start_time/end_time` servent aux recurrences et aux plages.

Timezone :

- le scheduler a ete ajuste pour lire `/etc/timezone` via `dateutil.tz`, comme d'autres modules.

## Audio - resume court

Notes detaillees dans :

```text
docs/audio-notes.md
```

Points clefs :

- probleme de volume / molette / casque;
- la carte est `tagtagtagsound`;
- `tagtagtag-mixerd` gere la molette et la config audio;
- config : `/var/lib/tagtagtag-sound/mixer.conf`;
- le mode courant reste :

```ini
lineout-mode=lineout
```

- `speaker-base` agit fortement sur le volume en mode lineout;
- `speaker-base=220` etait trop bas;
- etat juge acceptable :

```ini
tagtag-speaker-low=110
tagtag-speaker-high=130
speaker-base=255
lineout-mode=lineout
```

## Module Son - `nabsound`

Ajout d'un module web :

```text
http://nabaztag.local/sound/
```

Objectif :

- lire/modifier `/var/lib/tagtagtag-sound/mixer.conf`;
- afficher quelques etats ALSA;
- recharger `tagtagtag-mixerd`;
- reinitialiser ALSA;
- sauvegarder l'etat ALSA manuellement.

Fichiers :

```text
nabsound/
nabweb/settings.py
nabweb/urls.py
nabweb/templates/nabweb/_base.html
```

Pas de migration.

Correction faite :

- `pkill -USR1 tagtagtag-mixerd` echouait;
- utiliser :

```bash
pkill -USR1 -f tagtagtag-mixerd
```

Erreur corrigee :

- `TemplateSyntaxError`: les variables Django ne peuvent pas commencer par `_`;
- remplacer `config._error` par `config_error`.

## Fichier temporaire sound_alsa.lapin.py

`sound_alsa.lapin.py` est une copie locale de comparaison de :

```text
/opt/pynab-vifra/nabd/sound_alsa.py
```

Il n'est pas utilise par le projet.

Ne pas commiter.

Peut etre supprime :

```powershell
Remove-Item .\sound_alsa.lapin.py
```

Difference observee :

- version lapin recuperee streamait toutes les URLs HTTP/HTTPS;
- version locale stream seulement les URLs HTTP/HTTPS finissant par `.mp3`.

Cette difference n'explique pas le probleme de volume.

## Commandes utiles recentes

Verifier service planificateur :

```bash
systemctl status nabplannerd.service --no-pager
journalctl -u nabplannerd.service --since "30 minutes ago" --no-pager
```

Verifier mixerd :

```bash
systemctl status tagtagtag-mixerd.service --no-pager
ps aux | grep tagtagtag-mixerd
journalctl -u tagtagtag-mixerd.service --since "5 minutes ago" --no-pager
```

Recharger mixerd :

```bash
sudo pkill -USR1 -f tagtagtag-mixerd
```

Redemarrer mixerd :

```bash
sudo systemctl restart tagtagtag-mixerd.service
```

Reset audio prudent :

```bash
sudo systemctl stop nabd.socket
sudo systemctl stop nabd.service
sudo alsactl init 0
sudo systemctl start nabd.socket
sudo systemctl start nabd.service
```

Sauvegarder etat ALSA seulement si l'etat est bon :

```bash
sudo alsactl store
```

## A surveiller avant commit

Fichier temporaire a ne pas commiter :

```text
sound_alsa.lapin.py
```

Verifier les changements :

```bash
git status --short
git diff --stat
```

Il peut y avoir des changements utilisateur ou non relies. Ne pas les effacer sans verification.
