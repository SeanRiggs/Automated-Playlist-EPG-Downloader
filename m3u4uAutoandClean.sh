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

# Copy playlist to m3u directory for Docker processing
cp "$M3UFILES_DIR/playlist.m3u" "$M3UFILES_DIR/m3u/playlist.m3u"
echo "Copied playlist to m3u directory for docker m3u cleaner processing at $(date)" >> $LOGFILE

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

# Run the Docker container to clean and validate the playlist
echo "Starting m3u playlist cleaner at $(date)" >> $LOGFILE
docker run -ti --rm -v "$M3UFILES_DIR/m3u":/var/tmp/m3u m3u-playlist-cleaner
if [ $? -eq 0 ]; then
    echo "m3u playlist cleaner completed successfully at $(date)" >> $LOGFILE
    # Copy the validated playlist back to the original directory
    cp "$M3UFILES_DIR/m3u/playlist.m3u" "$M3UFILES_DIR/playlist.m3u"
    echo "Validated playlist copied back to $M3UFILES_DIR at $(date)" >> $LOGFILE
else
    echo "m3u playlist cleaner failed at $(date)" >> $LOGFILE
fi

# Check for log output indicating removed channels
if [ -s "$M3UFILES_DIR/m3u/validator.log" ]; then
    echo "Channels removed by cleaner:" >> $LOGFILE
    removed_count=$(grep 'does not have a valid stream; skipping.' "$M3UFILES_DIR/m3u/validator.log" | wc -l)
    echo "$removed_count channels were removed because they did not have valid streams." >> $LOGFILE
    grep 'does not have a valid stream; skipping.' "$M3UFILES_DIR/m3u/validator.log" >> $LOGFILE
else
    echo "No channels were removed by cleaner or log file not found." >> $LOGFILE
fi

echo "Script ended at $(date)" >> $LOGFILE