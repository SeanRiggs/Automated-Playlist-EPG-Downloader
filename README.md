# [![Typing SVG](https://readme-typing-svg.demolab.com?font=Fira+Code&pause=1000&color=510EF7&width=435&lines=Automate+Playlist+and+EPG+Downloads)](https://git.io/typing-svg)
## Overview

This repository provides a simple, automated solution for downloading M3U playlists and EPG (Electronic Program Guide) files using **m3u4u.com**, one of the most powerful tools available for managing IPTV playlists and EPG data. 

By leveraging the flexibility and customization that **m3u4u** offers, users can automate the process of fetching updated playlists and EPGs while avoiding being banned for exceeding server rate limits. This solution allows media server software, such as **Jellyfin**, **Plex**, **Emby**, or **Kodi**, to pull the latest TV data from a local directory, reducing the need for repeated requests to the server.

## Why Use **m3u4u**?

**m3u4u** is a feature-rich platform that simplifies the management of IPTV playlists and EPGs. Here’s why it’s the recommended choice:

- **Customizable Playlists**: You can create and organize your IPTV channels exactly the way you want, grouping them by category, adding custom names, and filtering out channels you don’t need.
- **EPG Integration**: It supports powerful EPG management, pulling from various sources and automatically aligning your channels with the correct program data.
- **URL-Based Access**: **m3u4u** generates URLs for your playlist and EPG, which can be easily integrated into media server software. This flexibility makes it a fantastic choice for automating live TV solutions.
- **Rate Limit Protection**: Like most IPTV and EPG services, **m3u4u** enforces rate limits on the number of requests made. To prevent getting banned for frequent updates, this script will download the latest files only once every 24 hours, ensuring compliance with their policies.
  
This repository focuses on automating the download process to fully take advantage of **m3u4u**'s abilities. It ensures your media server pulls live TV data from a local source and reduces the risk of server overload.

## Features

- **Automated Downloads**: Pulls your playlist and EPG data directly from **m3u4u.com** every 24 hours.
- **Local Caching**: The script stores the files locally so that your media server can pull data without making multiple requests to external servers.
- **Error Logging**: Tracks download attempts and logs any errors.
- **Customizable Paths**: Allows easy configuration of where the files are stored on your system.
  
## How It Works

The script automates downloading your M3U playlist and EPG files from **m3u4u.com**. It stores these files in a local directory, updating them daily without triggering excessive requests to **m3u4u**'s servers. Your media server software (such as Jellyfin or Plex) is then configured to pull the data from these locally stored files, ensuring up-to-date information with minimal server impact.

## Requirements

- **Git** for cloning this repository.
- **dos2unix** to ensure the script runs smoothly on UNIX-based systems.
- **cURL** to handle file downloads from the web.
  
## Installation

### Step 1: Clone the Repository

First, clone this repository to your local machine:

```bash
git clone https://github.com/SeanRiggs/automated-playlist-epg-downloader.git
cd automated-playlist-epg-downloader
```
### Step 2: Install Necessary Utilities
Ensure you have the necessary tools installed:
```bash
sudo apt-get update
sudo apt-get install git dos2unix curl
```
### Step 3: Create Directories
Set up directories for your playlist and EPG files:
```bash
mkdir -p /opt/mediastream/m3ufiles/m3u
```

### Step 4: Configure m3u4u
- Create an Account: Head over to Link: m3u4u.com and create an account.
- Add Your IPTV Playlist: Follow the instructions on m3u4u to add your IPTV provider’s M3U URL and organize your channels. Use m3u4u’s powerful grouping, filtering, and channel management features to customize the playlist to your preferences.
- Set Up EPG: Configure your guide data using m3u4u's EPG Manager. Assign channel logos, align channels with EPG sources, and generate the XML guide.
- **Copy URLs:*** Once your playlist and EPG are set up, copy the M3U and XML URLs provided by m3u4u. <i>** When copying the EPG URL, select the alternative non-compressed XML format vs. EPG.</i>

### Step 5: Modify the Script
Edit the script to include your m3u4u URLs:

```bash
#!/bin/sh

LOGFILE="/opt/mediastream/m3ufiles/m3u4u.log"
M3UFILES_DIR="/opt/mediastream/m3ufiles"

echo "Script started at $(date)" >> $LOGFILE

# Backup the existing playlist
if [ -f "$M3UFILES_DIR/playlist.m3u" ]; then
    cp "$M3UFILES_DIR/playlist.m3u" "$M3UFILES_DIR/playlist_backup.m3u"
    echo "Backup of playlist.m3u created at $(date)" >> $LOGFILE
else
    echo "playlist.m3u does not exist at $(date)" >> $LOGFILE
fi

# Download the latest playlist from m3u4u
curl http://m3u4u.com/m3u/YOUR_PLAYLIST_URL -o "$M3UFILES_DIR/playlist.m3u" -f -s
if [ $? -eq 0 ]; then
    echo "Downloaded playlist.m3u from m3u4u.com at $(date)" >> $LOGFILE
else
    echo "Failed to download playlist.m3u from m3u4u.com at $(date)" >> $LOGFILE
fi

# Pause to avoid rate limit issues
sleep 60

# Download the latest EPG from m3u4u
curl http://m3u4u.com/xml/YOUR_EPG_URL -o "$M3UFILES_DIR/epg.xml" -f -s
if [ $? -eq 0 ]; then
    echo "Downloaded epg.xml from m3u4u.com at $(date)" >> $LOGFILE
else
    echo "Failed to download epg.xml from m3u4u.com at $(date)" >> $LOGFILE
fi

echo "Script ended at $(date)" >> $LOGFILE
```
### Step 6: Automate with Cron
To ensure the script runs daily, create a cron job:
```bash
crontab -e
```
Add this line to run the script every day at 2 AM:
```bash
0 2 * * * /path/to/your/script.sh >> /opt/mediastream/m3ufiles/m3u4u.log 2>&1
```
## Example Configuration for Media Servers
Once the script is running and the files are being updated regularly, configure your media server to use the local paths for the playlist and EPG:

Jellyfin: In "Live TV" settings, point the Playlist and EPG to /opt/mediastream/m3ufiles/playlist.m3u and /opt/mediastream/m3ufiles/epg.xml.
Plex: In "Live TV & DVR" settings, specify the same local paths for the playlist and EPG files.

## Contributing
Contributions are welcome! Feel free to open an issue or submit a pull request if you encounter issues or have suggestions.

## License
This project is licensed under the MIT License.



