### The <code>m3u4uAutoandClean.sh</code> File

This file will perform the auto download like the standalone <code>m3u4u.sh</code>. However, it also has the automated docker m3u-playlist-cleaner container script included.

That is found on my GitHub here: link: https://github.com/SeanRiggs/m3u-playlist-cleaner

## How to install this version:
Create a path that you will clone the projects into. for example: 
```bash
sudo mkdir /opt/mediastream/m3ufiles
```
also, make a m3u directory for docker processing: 
```bash
sudo mkdir /opt/mediastream/m3ufiles/m3u
```
## Clone the m3u-playlist-cleaner here: 
```bash
cd /opt/mediastream/m3ufiles
git clone https://github.com/SeanRiggs/m3u-playlist-cleaner.git
```
you do not need to build the docker image as per the m3u-playlist-cleaner ReadME, as the auto script uses the prebuilt image

## Clone this repo to the same directory: 
In/opt/mediastream/m3ufiles (or whatever path you built for your m3uFiles): 
```bash
git clone https://github.com/SeanRiggs/automated-playlist-epg-downloader.git
```
### Resulting file structure:
<i>Move files as needed if you downloaded zip to match the structure below as this is what the script is expecting</i>
```bash
/opt/mediastream/m3ufiles
├── m3u
│   └── playlist.m3u (when copied after the first run)
├── m3u-playlist-cleaner
│   ├── Dockerfile
│   ├── composer.lock
│   ├── composer.php
│   ├── playlist_validator.php
│   └── vendor
│       └── (all vendor files here)
├── m3u4u.sh
└── m3u4uAutoandClean.sh
```

## Install all the dependencies:
```bash
sudo apt-get update
sudo apt-get install git dos2unix curl
``
**install docker**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
```
Run install script:
```bash
sudo sh get-docker.sh
```
Start And Enable Docker:
```docker
sudo systemctl start docker
sudo systemctl enable docker
```
Add your user to the “docker” group to run Docker commands without sudo:
```bash
sudo usermod -aG docker $USER
```
 make the script executable:
```bash
chmod +x /opt/mediastream/m3ufiles/m3u4uAutoandClean.sh
```

Automate with Cron
To ensure the script runs daily, create a cron job:
```bash
crontab -e
```
Add this line to run the script every day at 2 AM:
```bash
0 2 * * * /opt/mediastream/m3ufiles/m3u4uAutoandClean.sh >> /opt/mediastream/m3ufiles/m3u4u.log 2>&1
```
### Modify the Configurable Varriables in in the m3u4uAutoandClean.sh Script
Use a text editor or VSCode to edit the script to include your m3u4u URLs or any directory you may have changed:
**example in script:**
```bash
#!/bin/sh

# Configuration variables
LOGFILE="/opt/mediastream/m3ufiles/m3u4u.log"
M3UFILES_DIR="/opt/mediastream/m3ufiles"
PLAYLIST_URL="http://m3u4u.com/m3u/YOUR_PLAYLIST_URL"
EPG_URL="http://m3u4u.com/xml/YOUR_EPG_URL"
```
