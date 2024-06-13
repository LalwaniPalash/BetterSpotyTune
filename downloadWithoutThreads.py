import json
import logging
import os
import re
import shutil
import time
import unicodedata

import lyricsgenius
import mutagen
import requests
import spotipy
import yt_dlp
from dotenv import load_dotenv
from langdetect import detect
from mutagen import File
from mutagen.easymp4 import EasyMP4
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, ID3NoHeaderError, TPE1, TALB, TPE2, TDRC, APIC, USLT
from mutagen.mp4 import MP4, MP4Cover
from mutagen.wave import WAVE
from requests.exceptions import HTTPError
from spotipy.oauth2 import SpotifyClientCredentials
from youtube_search import YoutubeSearch

from langMap import languageMapping

logging.basicConfig(
    filename='spotifyDownloader.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Used to stop output from yt-dlp in Terminal
class NoOpLogger(logging.Logger):
    def __init__(self):
        super().__init__(self)
    
    def debug(self, msg, *args, **kwargs):
        pass
    
    def info(self, msg, *args, **kwargs):
        pass
    
    def warning(self, msg, *args, **kwargs):
        pass
    
    def error(self, msg, *args, **kwargs):
        pass
    
    def exception(self, msg, *args, exc_info=True, **kwargs):
        pass
    
    def critical(self, msg, *args, **kwargs):
        pass

# Prompts the user to select the download format for playlist(s)
def selectAudioFormat():
    print()
    print("Select audio format:")
    print("1. MP3")
    print("2. WAV")
    print("3. FLAC")
    print("4. M4A")
    
    while True:
        choice = input("Enter the number corresponding to the desired format: ")
        if choice in ['1', '2', '3', '4']:
            return choice
        else:
            print("Invalid input. Please enter a number between 1 and 4.")

selectedFormat = selectAudioFormat()

# Defining the formats and corresponding preferred codecs
formats = {
    '1': ('mp3', '192'),
    '2': ('wav', None),
    '3': ('flac', None),
    '4': ('m4a', '192')
}

# Set the selected format's preferred codec and quality
preferredCodec = formats[selectedFormat][0]
preferredQuality = formats[selectedFormat][1]

# Function to download audio
def downloadAudio(url, outputPath, title):
    ydlOpts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(outputPath, f'{title}.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': preferredCodec,
            'preferredquality': preferredQuality,
        }] if preferredCodec else [],
        'quiet': True,
        'no_warnings': True,
        'logger': NoOpLogger(),
    }
    try:
        with yt_dlp.YoutubeDL(ydlOpts) as ydl:
            logging.info(f"\nDownloading audio for {title} from {url}\n")
            ydl.download([url])
            logging.info(f"Successfully downloaded audio for {title}\n")
            print(f"Downloaded: {title}")
            return True
    except Exception as e:
        logging.error(f"Error downloading audio: {e}\n")
        return False

# Function to retry an operation
def retry(operation, attempts, delay):
    for attempt in range(attempts):
        try:
            result = operation()
            if result:
                return result
        except Exception as e:
            logging.warning(f"Attempt {attempt + 1} failed: {e}\n")
        print(f"Retrying in {delay} seconds...")
        time.sleep(delay)
    logging.error(f"All {attempts} attempts failed.\n")
    return None

# Function to download audio with retry functionality
def downloadAudioWithRetry(url, outputPath, title, attempts=3, delay=5):
    def operation():
        return downloadAudio(url, outputPath, title)
    return retry(operation, attempts, delay)

# Converting 2 alphabet code to 3 alphabet code
def convertLangIso(lang):
    convertedLanguage = languageMapping.get(lang)
    if not convertedLanguage:
        raise ValueError(f"No language mapping found for {lang}")
    return convertedLanguage

# Function to get lyrics from lyrics.ovh, if it fails then tries to get lyrics from Genius
def getLyrics(artist, trackTitle):
    try:
        artistName = unicodedata.normalize('NFKD', artist)
        artistName = ''.join([c for c in artistName if not unicodedata.combining(c)])
        artistName = artistName.replace(",", "").replace(".", "")
        artistFormatted = re.sub(r"\s+", "-", artistName.lower())
        
        trackTitleName = unicodedata.normalize('NFKD', trackTitle)
        trackTitleName = ''.join([c for c in trackTitleName if not unicodedata.combining(c)])
        trackTitleName = trackTitleName.replace(",", "").replace(".", "")
        trackTitleFormatted = re.sub(r"\s+", "-", trackTitleName.lower())
        
        # Create a Genius URL for the song
        url = f"https://genius.com/{artistFormatted}-{trackTitleFormatted}-lyrics"
        
        # Fetch lyrics using the URL
        try:
            lyrics = genius.lyrics(song_url=url)
        except requests.exceptions.HTTPError as httpe:
            logging.info("Song lyrics not found, attempting to search...\n")
            song = genius.search_song(title=trackTitle, artist=artist)
            if song:
                logging.info(f"Found lyrics for {trackTitle} by {artist} through search.\n")
                return song.lyrics
            else:
                logging.error(f"Lyrics not found for {trackTitle} by {artist}.\n")
                return "No lyrics found"
        return lyrics
    except Exception as e:
        logging.error(f"Error fetching lyrics from Genius for {trackTitle} by {artist}: {e}\n")
        return "No lyrics found"

# Function to add ID3 tags
def addId3Tags(audio, filePath, trackTitle, artist, albumName, albumArtists, releaseDate, imageUrl):
    audio.add(TPE1(encoding=3, text=artist))
    audio.add(TALB(encoding=3, text=albumName))
    audio.add(TPE2(encoding=3, text=albumArtists))
    audio.add(TDRC(encoding=3, text=releaseDate))

    try:
        imageResponse = requests.get(imageUrl)
        imageResponse.raise_for_status()
        imageData = imageResponse.content
        mimeType = "image/jpeg"
        image = APIC(
            encoding=3,
            mime=mimeType,
            type=3,
            desc=os.path.basename(imageUrl),
            data=imageData,
        )
        audio.delall("APIC")
        audio.add(image)
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to download or embed album art for {trackTitle} by {artist}: {e}\n")

    try:
        lyrics = getLyrics(artist, trackTitle)
        if lyrics:
            lyricsLang = convertLangIso(detect(lyrics))
            audio.add(USLT(encoding=3, lang=lyricsLang, desc=u'desc', text=lyrics))
    except Exception as e:
        logging.error(f"Error adding lyrics for {trackTitle} by {artist}: {e}\n")

    audio.save(filePath)

# Function to update metadata of different mp3, wav, flac, and m4a
def updateMetadata(filePath, trackTitle, artist, albumName, albumArtists, releaseDate, imageUrl):
    fileFormat = filePath.split('.')[-1].lower()
    try:
        if fileFormat == "mp3":
            try:
                audio = ID3(filePath)
                addId3Tags(audio, filePath, trackTitle, artist, albumName, albumArtists, releaseDate, imageUrl)
            except ID3NoHeaderError:
                logging.error(f"ID3NoHeaderError: No ID3 header found in the file for {trackTitle} by {artist}.\n")

        elif fileFormat == "wav":
            try:
                audio = WAVE(filePath)
                id3 = ID3()
                addId3Tags(id3, filePath, trackTitle, artist, albumName, albumArtists, releaseDate, imageUrl)
                id3.save(filePath)
            except ID3NoHeaderError:
                logging.error(f"ID3NoHeaderError: No ID3 header found in the file for {trackTitle} by {artist}\n")

        elif fileFormat == "flac":
            try:
                audio = FLAC(filePath)
                audio["title"] = trackTitle
                audio["artist"] = artist
                audio["album"] = albumName
                audio['albumartist'] = albumArtists
                audio["date"] = releaseDate

                imageResponse = requests.get(imageUrl)
                imageResponse.raise_for_status()
                imageData = imageResponse.content
                picture = Picture()
                picture.data = imageData
                picture.mime = "image/jpeg"
                picture.type = mutagen.id3.PictureType.COVER_FRONT
                audio.clear_pictures()
                audio.add_picture(picture)

                try:
                    lyrics = getLyrics(artist, trackTitle)
                    if lyrics:
                        audio["LYRICS"] = lyrics
                except Exception as e:
                    logging.error(f"Error adding lyrics for {trackTitle} by {artist}: {e}\n")

                audio.save()
            except Exception as e:
                logging.error(f"Error saving metadata for {trackTitle} by {artist}: {e}\n")

        elif fileFormat == "m4a":
            try:
                audio = EasyMP4(filePath)
                audio['title'] = trackTitle
                audio['artist'] = artist
                audio['album'] = albumName
                audio['albumartist'] = albumArtists
                audio['date'] = releaseDate
                audio.save()

                try:
                    imageResponse = requests.get(imageUrl)
                    imageResponse.raise_for_status()
                    imageData = imageResponse.content
                    audio = MP4(filePath)
                    audio.tags['covr'] = [MP4Cover(imageData, imageformat=MP4Cover.FORMAT_JPEG)]
                except requests.exceptions.RequestException as e:
                    logging.error(f"Failed to download or embed album art for {trackTitle} by {artist}: {e}\n")
                try:
                    lyrics = getLyrics(artist, trackTitle)
                    if lyrics:
                        audio["\xa9lyr"] = lyrics
                except Exception as e:
                    logging.error(f"Error adding lyrics for {trackTitle} by {artist}: {e}\n")
                audio.save()
                

            except FileNotFoundError as e:
                logging.error(f"FileNotFoundError: File not found for {trackTitle} by {artist}\n")

    except Exception as e:
        logging.error(f"Error saving metadata for {trackTitle} by {artist}: {e}\n")

# Function to get playlist data
def processPlaylist(playlistLink, baseOutputPath):
    match = re.match(r"https://open.spotify.com/playlist/(\w+)", playlistLink)
    if match:
        playlistUri = match.groups()[0]
    else:
        raise ValueError("Expected format: https://open.spotify.com/playlist/...")

    playlist = session.playlist(playlistUri)
    playlistName = playlist['name']
    sanitizedPlaylistName = "".join(char for char in playlistName if char.isalnum() or char in (' ', '_', '-')).rstrip()
    if not sanitizedPlaylistName:
        sanitizedPlaylistName = "playlist"
    playlistDir = os.path.join(baseOutputPath, sanitizedPlaylistName)
    os.makedirs(playlistDir, exist_ok=True)

    print(f"Processing playlist: {playlistName}")

    playlistData = playlist["tracks"]["items"]

    # Function to get data of a track and download it.
    for track in playlistData:
        name = track["track"]["name"]
        artists = ", ".join([artist["name"] for artist in track["track"]["artists"]])
        image = track["track"]["album"]["images"][0]["url"]
        albumName = track["track"]["album"]["name"]
        albumArtists = ", ".join([artist["name"] for artist in track["track"]["album"]["artists"]])
        releaseDate = track["track"]["album"]["release_date"]
        trackTitle = f"{name} (Official Audio) - {artists}"
    
        searchResult = YoutubeSearch(trackTitle, max_results=1).to_json()
        resultData = json.loads(searchResult)
        if resultData['videos']:
            urlSuffix = resultData['videos'][0]['url_suffix']
            youtubeUrl = f"https://www.youtube.com{urlSuffix}"
            try:
                # Prefix the file name with the index to retain order
                formattedName = f"{index + 1:02d} - {name}"
                downloadAudioWithRetry(youtubeUrl, playlistDir, formattedName)
                fileExtension = preferredCodec
                filePath = os.path.join(playlistDir, f"{formattedName}.{fileExtension}")
                updateMetadata(filePath, name, artists, albumName, albumArtists, releaseDate, image)
            except Exception as e:
                logging.error(f"Error processing track {name}: {e}\n")
        else:
            print(f"No YouTube results for: {trackTitle}")

# Function which I use to move the downlaoded playlist to Apple Music's Directory
def autoImport2AppleMusic(playlistDir):
    try:
        musicDir = "<Enter your Music Directory>"
        # Try to move the folder to destination
        shutil.move(playlistDir, musicDir)
        print("Playlist folder moved successfully.")
    except Exception as e:
        print(f"Error moving playlist folder: {e}")

# Main execution
load_dotenv()

# Get the necessary info from .env file
clientId = os.getenv("CLIENT_ID")
clientSecret = os.getenv("CLIENT_SECRET")
geniusAccessToken = os.getenv("GENIUS_ACCESS_TOKEN")

genius = lyricsgenius.Genius(geniusAccessToken, verbose=False)
clientCredentialsManager = SpotifyClientCredentials(client_id=clientId, client_secret=clientSecret)
session = spotipy.Spotify(client_credentials_manager=clientCredentialsManager)

"""
Format should be: 
playlistLinks = [
    "Playlist 1",
    "Playlist 2",
         .
    "Playlist n"
]
"""
# List of playlist to be downloaded
playlistLinks = [
    "Add your own playlist link(s)"
]

# Output path where the playlist should be downloaded 
outputPath = "Set your output Path"

# Open the Log file
with open('spotifyDownloader.log', 'w'):
    pass

# Loop over each playlist
for playlistLink in playlistLinks:
    processPlaylist(playlistLink, outputPath)

logging.info("Process complete.")
