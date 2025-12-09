from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from spotdl import Song
from spotdl.utils.spotify import SpotifyClient
import logging
import os
import json
import subprocess
import uuid
import shutil

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

# --- Mission 3: Downloader ---

class DownloadRequest(BaseModel):
    urls: list[str]

def cleanup_files(folder_path: str, zip_path: str):
    """Deletes the temporary download folder and the zip file."""
    try:
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)
        if os.path.exists(zip_path):
            os.remove(zip_path)
        logger.info(f"Cleaned up {folder_path} and {zip_path}")
    except Exception as e:
        logger.error(f"Error cleaning up files: {e}")

@app.post("/download_batch")
def download_batch(request: DownloadRequest, background_tasks: BackgroundTasks):
    """
    Downloads list of songs using spotdl, zips them, and returns the zip file.
    Warning: blocking operation, may timeout for large lists.
    """
    session_id = str(uuid.uuid4())
    base_dir = os.getcwd() # Should be .../backend
    temp_dir = os.path.join(base_dir, "temp_downloads", session_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    songs_file = os.path.join(temp_dir, "songs.txt")
    zip_filename = f"spotify_download_{session_id}"
    zip_path = os.path.join(base_dir, "temp_downloads", f"{zip_filename}.zip")

    logger.info(f"Starting batch download sesion (Fixed Args): {session_id} for {len(request.urls)} songs")

    try:
        # Step B: Write songs.txt
        with open(songs_file, "w") as f:
            for url in request.urls:
                f.write(url + "\n")

        # Step C: Execute spotdl
        # Note: We assume spotdl is in venv/bin/spotdl relative to current working dir (backend)
        spotdl_bin = os.path.join(base_dir, "venv", "bin", "spotdl")
        if not os.path.exists(spotdl_bin):
            # Fallback to system spotdl if not in venv
            spotdl_bin = "spotdl"

        # Validation: Check if files exist
        song_list = []
        with open(songs_file, "r") as f:
             song_list = [line.strip() for line in f if line.strip()]

        # Construct command
        # --simple-tui to reduce log noise
        # Pass URLs directly as arguments to avoid file detection issues
        cmd = [
            spotdl_bin,
            "download", # Explicitly state operation
            *song_list,
            "--overwrite", "force",
            "--simple-tui" 
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        
        # Run subprocess with timeout
        result = subprocess.run(
            cmd,
            cwd=temp_dir, # Run inside the temp directory
            check=True,
            timeout=300, # 5 minutes timeout
            capture_output=True
        )
        logger.info(f"Spotdl Output: {result.stdout.decode() if result.stdout else 'No stdout'}")

        # Validation: Check if files exist
        downloaded_files = os.listdir(temp_dir)
        downloaded_files = [f for f in downloaded_files if f != "songs.txt"]
        if not downloaded_files:
             logger.error("No files downloaded, but spotdl exited 0.")
             # Attempt to find where it might have gone? No, just fail.
             raise Exception("Spotdl finished but no files were found in output directory.")

        # Step D: Package (Zip)
        # make_archive expects base_name (without extension) and root_dir
        shutil.make_archive(
            os.path.join(base_dir, "temp_downloads", zip_filename),
            'zip',
            temp_dir
        )
        
        if not os.path.exists(zip_path):
            raise Exception("Zip file was not created")

        # Step E: Return & Cleanup
        background_tasks.add_task(cleanup_files, temp_dir, zip_path)
        
        return FileResponse(
            zip_path, 
            media_type='application/zip', 
            filename="spotify_download.zip"
        )

    except subprocess.CalledProcessError as e:
        error_msg = f"Spotdl failed: {e.stderr.decode() if e.stderr else 'No stderr'} | Output: {e.stdout.decode() if e.stdout else 'No stdout'}"
        logger.error(error_msg)
        cleanup_files(temp_dir, zip_path) # Cleanup on failure
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")
    except subprocess.TimeoutExpired:
        logger.error("Download timed out")
        cleanup_files(temp_dir, zip_path)
        raise HTTPException(status_code=504, detail="Download timed out (limit 5 mins)")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        cleanup_files(temp_dir, zip_path)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
@app.get("/analyze_stream")
def analyze_stream(url: str):
    """
    Streams analysis progress for a playlist.
    Yields JSON lines: {"progress": X, "total": Y, "tracks": [...]}
    """
    logger.info(f"Streaming analysis for URL: {url}")
    
    def event_generator():
        # 1. Init Client (Already done globally)
        client = SpotifyClient()
        
        # 2. Check if playlist
        if "playlist" not in url and "album" not in url:
            # Fallback for single songs -> just return one chunk
            try:
                songs = Song.from_url(url)
                if not isinstance(songs, list):
                     songs = [songs]
                
                data = []
                for song in songs:
                    data.append({
                        "title": song.name,
                        "artist": song.artist,
                        "album": song.album_name,
                        "duration": song.duration,
                        "url": song.url,
                        "cover_url": song.cover_url
                    })
                yield json.dumps({"progress": 1, "total": 1, "tracks": data}) + "\n"
                return
            except Exception as e:
                yield json.dumps({"error": str(e)}) + "\n"
                return

        # 3. Handle Playlist/Album Pagination
        try:
            results_chunk = []
            total_tracks = 0
            
            # Simplified logic: use spotdl's internal pagination access
            # We can't use Playlist.from_url() easily because it blocks.
            # We must use SpotifyClient directly.
            
            if "playlist" in url:
                resp = client.playlist_items(url)
                total_tracks = client.playlist(url)['tracks']['total']
            else:
                resp = client.album_tracks(url) # Spotipy method
                total_tracks = client.album(url)['total_tracks'] # might vary slightly for albums
            
            fetched_count = 0
            
            while True:
                items = resp['items']
                chunk_songs = []
                
                for item in items:
                    # Handle difference between playlist item (wrapped) and album track (direct)
                    track_data = item.get('track', item) 
                    
                    if not track_data or track_data.get('is_local'):
                        continue
                        
                    # Minimal extraction for speed (fetching full Song object via spotdl logic is heavy)
                    # We just need display info
                    
                    artists = [a['name'] for a in track_data.get('artists', [])]
                    album_name = track_data.get('album', {}).get('name', 'Unknown')
                    
                    # Cover URL is tricky for tracks vs playlist items.
                    # Playlist items usually have it in track.album.images
                    cover_url = ""
                    if track_data.get('album') and track_data['album'].get('images'):
                         cover_url = track_data['album']['images'][0]['url']
                    
                    song_obj = {
                        "title": track_data.get('name'),
                        "artist": ", ".join(artists),
                        "album": album_name,
                        "duration": int(track_data.get('duration_ms', 0) / 1000),
                        "url": track_data.get('external_urls', {}).get('spotify'),
                        "cover_url": cover_url
                    }
                    chunk_songs.append(song_obj)
                
                fetched_count += len(items)
                
                # Yield this batch
                yield json.dumps({
                    "progress": fetched_count,
                    "total": total_tracks,
                    "tracks": chunk_songs
                }) + "\n"
                
                # Next page
                if resp.get('next'):
                    resp = client.next(resp)
                else:
                    break
                    
        except Exception as e:
             logger.error(f"Stream Error: {e}")
             yield json.dumps({"error": str(e)}) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
