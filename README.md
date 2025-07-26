
npm install
npm install express

Sur Powershell :
pip install "yt-dlp[default,curl-cffi]"
pip install psutil
En mode administrateur :
choco install ffmpeg

Sur WSL :
sudo apt install ffmpeg
sudo apt install python3.12-venv
python3 -m venv myenv
source /mnt/c/Users/USERNAME/Documents/myenv/bin/activate
python3 -m pip install -U yt-dlp
pip install psutil
deactivate

Pour rediriger les requête du port 2000 du pc vers celui de wsl :
BASH :
hostname -I
Powershell (en admin) :
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=2000 connectaddress=IP_WSL connectport=2000

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

