from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from spotdl import Song
from spotdl.utils.spotify import SpotifyClient
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize SpotifyClient with spotdl's default "anonymous" credentials
# These are the same keys used by the spotdl CLI
DEFAULT_CLIENT_ID = "5f573c9620494bae87890c0f08a60293"
DEFAULT_CLIENT_SECRET = "212476d9b0f3472eaa762d90b19b0ba8"

try:
    SpotifyClient.init(client_id=DEFAULT_CLIENT_ID, client_secret=DEFAULT_CLIENT_SECRET)
except Exception as e:
    logger.warning(f"SpotifyClient init warning (might be already initialized): {e}")

app = FastAPI(title="Spotify Downloader - Metadata Service")

class PlaylistRequest(BaseModel):
    url: str

@app.post("/analyze")
def analyze_playlist(request: PlaylistRequest):
    """
    Analyzes a Spotify playlist URL using spotdl and returns metadata.
    """
    try:
        logger.info(f"Analyzing URL: {request.url}")
        
        # Determine type of URL and fetch accordingly
        if "playlist" in request.url:
            from spotdl.types.playlist import Playlist
            playlist = Playlist.from_url(request.url)
            songs = playlist.songs
        elif "album" in request.url:
            from spotdl.types.album import Album
            album = Album.from_url(request.url)
            songs = album.songs
        else:
            # Assume single song
            songs = Song.from_url(request.url)
            if not isinstance(songs, list):
                songs = [songs]
            
        results = []
        for song in songs:
            results.append({
                "title": song.name,
                "artist": song.artist,
                "album": song.album_name,
                "duration": song.duration,
                "url": song.url,
                "cover_url": song.cover_url
            })
            
        return {
            "input_url": request.url,
            "track_count": len(results),
            "tracks": results
        }
    except Exception as e:
        logger.error(f"Error analyzing playlist: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to analyze playlist: {str(e)}")

class DownloadRequest(BaseModel):
    urls: list[str]

@app.post("/download_batch")
def download_batch(request: DownloadRequest):
    """
    Placeholder for Mission 3. Returns a success message.
    """
    logger.info(f"Received batch download request for {len(request.urls)} urls")
    return {"message": "Batch download initiated", "count": len(request.urls)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
