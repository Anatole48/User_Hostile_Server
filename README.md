npm install
npm install express
pip install yt-dlp
pip install psutil

En mode administrateur :
choco install ffmpeg

Désinstaller/désactiver McAfee.

Vérifier dans "Ajouter une application facultative" que "Open SSH Client" et "Open SSH Server" soient installer.
Aller dans services que l'état de Open SSH Server soit "En Cours" et que le Type de Démarrage soit en "Automatique".

Sur Powershell, faire : ssh-keygen
Ensuite, aller dans : C:\Users\USERNAME\.ssh\authorized_keys
et coller la clé publique générer par le client.

Modifier le fichier C:\ProgramData\ssh\sshd_config pour avoir les lignes :
PubkeyAuthentication yes
AuthorizedKeysFile C:/Users/anato/.ssh/authorized_keys
PasswordAuthentication no
Mettre les lignes suivantes en commentaire :
#Match Group administrators
#       AuthorizedKeysFile __PROGRAMDATA__/ssh/administrators_authorized_keys


node .\server.js

