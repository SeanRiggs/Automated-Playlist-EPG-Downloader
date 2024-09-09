#!/bin/sh

# Configuration variables
LOGFILE="/opt/mediastream/m3ufiles/m3u4u.log"
M3UFILES_DIR="/opt/mediastream/m3ufiles"
PLAYLIST_URL="http://m3u4u.com/m3u/YOUR_PLAYLIST_URL"
EPG_URL="http://m3u4u.com/xml/YOUR_EPG_URL"

echo "Script started at $(date)" >> $LOGFILE

# Backup the existing playlist
if [ -f "$M3UFILES_DIR/playlist.m3u" ]; then
    cp "$M3UFILES_DIR/playlist.m3u" "$M3UFILES_DIR/playlist_backup.m3u"
    echo "Backup of playlist.m3u created at $(date)" >> $LOGFILE
else
    echo "playlist.m3u does not exist at $(date)" >> $LOGFILE
fi

# Download the latest playlist from m3u4u
PLAYLIST_ERROR=$(curl "$PLAYLIST_URL" -o "$M3UFILES_DIR/playlist.m3u" -f -s -S 2>&1)
if [ $? -ne 0 ]; then
    echo "Failed to download playlist.m3u from m3u4u.com at $(date)" >> $LOGFILE
    echo "Error: $PLAYLIST_ERROR" >> $LOGFILE
    echo "This error might mean: The URL is incorrect, m3u4u.com is down, or there's a network issue." >> $LOGFILE
    echo "Please check your PLAYLIST_URL and internet connection." >> $LOGFILE
    exit 1
fi
echo "Downloaded playlist.m3u from m3u4u.com at $(date)" >> $LOGFILE

# Pause to avoid rate limit issues
sleep 60

# Download the latest EPG from m3u4u
EPG_ERROR=$(curl "$EPG_URL" -o "$M3UFILES_DIR/epg.xml" -f -s -S 2>&1)
if [ $? -ne 0 ]; then
    echo "Failed to download epg.xml from m3u4u.com at $(date)" >> $LOGFILE
    echo "Error: $EPG_ERROR" >> $LOGFILE
    echo "This error might mean: The URL is incorrect, m3u4u.com is down, or there's a network issue." >> $LOGFILE
    echo "Please check your EPG_URL and internet connection." >> $LOGFILE
    exit 1
fi
echo "Downloaded epg.xml from m3u4u.com at $(date)" >> $LOGFILE

echo "Script ended at $(date)" >> $LOGFILE
