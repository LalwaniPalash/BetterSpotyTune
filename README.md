# Spotify Playlist Downloader

This project allows users to download playlists from Spotify, extract audio from YouTube, and update metadata including lyrics and album artwork.

## Features

- **Playlist Download:** Download playlists from Spotify using the playlist link.
- **Audio Extraction:** Extract audio tracks from YouTube videos.
- **Multiple Audio Formats:** Chosse from FLAC, MP3, M4A, or WAV
- **Metadata Update:** Update metadata including artist, album, release date, and lyrics.
- **Add Lyrics:** Unsynced lyrics also get added to the metadata.
- **Automatic Import:** Automatically import downloaded playlists to Apple Music. Tested on MacOS.

## Installation

1. Clone the repository: `git clone <repository-url>`
2. Install dependencies:
   - Python 3.x
   - Use pip to install dependencies: `pip install -r requirements.txt`

## Usage

1. Create a `.env` file and add your Spotify client ID, client secret, and Genius access token:

    ```env
    CLIENT_ID=your-client-id
    CLIENT_SECRET=your-client-secret
    GENIUS_ACCESS_TOKEN=your-genius-access-token
    ```
2. Run the script with the desired playlist link: `python main.py`
3. Follow the prompts to select the desired audio format and confirm the download.

## Known Errors
- Artwork Issue: Track artwork does not get added to .flac and .wav files.

## Contributing
- Contributions are welcome! Feel free to open issues or pull requests for any improvements or bug fixes.
