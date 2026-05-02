# Notes audio TagTagTag

Notes brutes prises pendant le diagnostic audio du 1er mai 2026.

## Symptomes observes

- Le volume du lapin etait tres fort.
- La molette ne modulait plus vraiment le volume.
- Casque branche :
  - au debut, molette eteinte : son casque seul dans certains etats;
  - apres activation de la molette : son casque + haut-parleur du lapin;
  - en coupant la molette ensuite : le son restait casque + haut-parleur.
- La prise jack fonctionne comme une sortie ligne avec la configuration actuelle, pas comme une prise casque qui coupe toujours le haut-parleur.

## Fichiers et services impliques

- Carte ALSA detectee :
  - `tagtagtagsound`
  - device : `plughw:CARD=tagtagtagsound`
- Driver/mixeur :
  - `/opt/wm8960`
  - `/usr/local/sbin/tagtagtag-mixerd -d`
  - service : `tagtagtag-mixerd.service`
- Configuration du mixeur :
  - `/var/lib/tagtagtag-sound/mixer.conf`
  - defaut : `/opt/wm8960/mixer.conf.default`
- Etat ALSA :
  - `/var/lib/alsa/asound.state`

## Commandes de diagnostic utiles

```bash
cat /proc/asound/cards
aplay -l
amixer scontrols
amixer contents
```

```bash
amixer cget numid=1
amixer cget numid=44
amixer cget numid=11
amixer cget numid=12
amixer cget numid=14
amixer cget numid=18
```

Correspondances observees :

- `numid=1` : `Headphones Jack`
- `numid=44` : `Volume Button`
- `numid=11` : `Playback Volume`
- `numid=12` : `Headphone Playback Volume`
- `numid=14` : `Speaker Playback Volume`
- `numid=18` : `PCM Playback -6dB Switch`
- `numid=54` : `Left Output Mixer PCM Playback Switch`
- `numid=57` : `Right Output Mixer PCM Playback Switch`
- `numid=60` : `Mono Output Mixer Left Switch`
- `numid=61` : `Mono Output Mixer Right Switch`

Test sonore :

```bash
speaker-test -D default -c 2 -t sine -l 3
speaker-test -D plughw:CARD=tagtagtagsound -c 2 -t sine -l 3
```

## Configuration tagtagtag-mixerd

Fichier :

```bash
/var/lib/tagtagtag-sound/mixer.conf
```

Etat garde comme acceptable :

```ini
debug=false
tag-speaker-low=121
tag-speaker-high=127
tagtag-speaker-low=110
tagtag-speaker-high=130
speaker-base=255
headphone-low=227
headphone-high=249
lineout-mode=lineout
microphone-enabled=true
input1-base=3
capture-base=90
```

Notes :

- `lineout-mode=lineout` : la sortie jack se comporte comme line out. Le commentaire du fichier indique que le son est au niveau `speaker-base`, quelle que soit la molette.
- `lineout-mode=headphone` : mode casque, cense muter les haut-parleurs quand le jack est branche. Non active pour l'instant.
- `speaker-base` est le parametre qui a clairement modifie le volume en mode `lineout`.
- `speaker-base=220` rendait le son tres bas.
- `speaker-base=255` avec les valeurs ci-dessus etait juge "pas trop mal".
- Les valeurs `tagtag-speaker-low/high` n'ont pas donne une modulation evidente dans l'etat teste.

Recharger le mixeur :

```bash
sudo pkill -USR1 -f tagtagtag-mixerd
```

Redemarrer le mixeur :

```bash
sudo systemctl restart tagtagtag-mixerd.service
```

Logs :

```bash
journalctl -u tagtagtag-mixerd.service --since "5 minutes ago" --no-pager
```

Debug :

```bash
sudo sed -i 's/^debug=.*/debug=true/' /var/lib/tagtagtag-sound/mixer.conf
sudo systemctl restart tagtagtag-mixerd.service
```

Revenir sans debug :

```bash
sudo sed -i 's/^debug=.*/debug=false/' /var/lib/tagtagtag-sound/mixer.conf
sudo systemctl restart tagtagtag-mixerd.service
```

## Observations sur la molette

`Volume Button` changeait entre :

```text
values=on,on
values=on,off
```

Le daemon a logge :

```text
Unexpected button values (both are high)
```

Interpretation prudente :

- La molette est lue via deux entrees GPIO :
  - `Volume_setting_1` -> `GPIO27`
  - `Volume_setting_2` -> `GPIO22`
- `tagtagtag-mixerd` attend des combinaisons valides.
- Quand il lit les deux entrees a high, il considere l'etat invalide et peut garder le dernier profil applique.
- La modulation fine n'a pas ete confirmee. Le comportement observe ressemble davantage a des profils/etats.

## Schema hardware

Depuis `Nabaztag_RPI_V2.0_specification.PDF`, signaux identifies :

- `Volume_setting_1` sur `GPIO27`
- `Volume_setting_2` sur `GPIO22`
- `GPIO08_AMP_MUTE`
- `GPIO07_AMP_PWR_SHDN`
- `Plug_detect`
- `RINPUT3/JD3`
- `HEADPHONE_L`
- `HEADPHONE_R`
- `SPK_1`
- `SPK_2`
- ampli haut-parleur : `MAX9759ETE+T`

Conclusion materielle probable :

- Le haut-parleur a un ampli separe.
- L'ampli haut-parleur est controle par des GPIO pris par le driver (`GPIO7` et `GPIO8` etaient `Device or resource busy`).
- La detection jack existe (`Headphones Jack` expose par ALSA).
- La coupure haut-parleur avec casque depend de la logique driver/mixerd, pas seulement des volumes ALSA.

## GPIO

Tests sysfs :

```bash
echo 8 | sudo tee /sys/class/gpio/export
```

Resultat :

```text
Device or resource busy
```

Idem pour GPIO7.

Conclusion :

- `GPIO7` et `GPIO8` sont probablement reserves par le driver audio/mixerd.
- Ils ne sont pas pilotables directement via `/sys/class/gpio`.

## ALSA init / restore

Reinitialisation qui a permis de retrouver un etat sain temporaire :

```bash
sudo systemctl stop nabd.socket
sudo systemctl stop nabd.service
sudo alsactl init 0
sudo alsactl store
sudo systemctl start nabd.socket
sudo systemctl start nabd.service
```

Attention :

- Ne pas lancer `sudo alsactl store` quand l'etat audio est mauvais, sinon il peut devenir l'etat restaure au demarrage.
- Dans l'image `pynab-v1.0.2-zero_raspbian.img`, `/var/lib/alsa/` etait vide. L'etat ALSA semble donc genere au boot/init plutot que fourni comme fichier sauvegarde.

Services ALSA dans l'image :

```text
alsa-restore.service
alsa-state.service
90-alsa-restore.rules
```

`alsa-restore.service` contient un `ExecStop` qui fait un `alsactl store`.

## Module web nabsound

Un module web `nabsound` a ete ajoute pour gerer une partie de cette configuration via :

```text
http://nabaztag.local/sound/
```

Fonctions prevues :

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

Correction faite :

- `pkill -USR1 tagtagtag-mixerd` echouait probablement car le nom de process est trop long/tronque.
- Le module utilise maintenant :

```bash
pkill -USR1 -f tagtagtag-mixerd
```

## Fichier temporaire

`sound_alsa.lapin.py` est une copie locale de comparaison recuperee depuis le lapin :

```powershell
scp pi@nabaztag.local:/opt/pynab-vifra/nabd/sound_alsa.py C:\Users\virgi\Documents\Perso\www\pynab-vifra\sound_alsa.lapin.py
```

Ce fichier n'est pas utilise par Pynab et ne doit pas etre commite.

Difference observee :

- version locale : stream HTTP/HTTPS seulement si l'URL finit par `.mp3`;
- version lapin recuperee : stream toute URL HTTP/HTTPS comme MP3.

Cette difference n'explique pas les problemes de volume/molette.

## Service NFC nabsound

Un service `nabsound` gere des tags NFC dedies au volume du haut-parleur du
lapin uniquement. Il ne change pas les reglages casque.

Actions encodees dans les tags :

- `mute` : met `speaker-base` a `0`;
- `up` : augmente `speaker-base` par pas de `15`;
- `down` : baisse `speaker-base` par pas de `15`;
- `reset` : remet `speaker-base` a `255`.

Apres chaque action, le service recharge `tagtagtag-mixerd` avec :

```bash
pkill -USR1 -f tagtagtag-mixerd
```
