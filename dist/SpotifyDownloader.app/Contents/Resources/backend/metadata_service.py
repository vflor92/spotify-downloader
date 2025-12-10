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

@app.get("/download_file/{session_id}")
def download_file(session_id: str, background_tasks: BackgroundTasks):
    """
    Serves the zip file for a given session ID and cleans up afterwards.
    """
    base_dir = os.getcwd()
    zip_path = os.path.join(base_dir, "temp_downloads", f"spotify_download_{session_id}.zip")
    temp_dir = os.path.join(base_dir, "temp_downloads", session_id)
    
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="File not found or expired")
        
    return FileResponse(
        zip_path, 
        media_type='application/zip', 
        filename="spotify_download.zip",
        background=background_tasks.add_task(cleanup_files, temp_dir, zip_path)
    )

@app.post("/download_batch")
def download_batch(request: DownloadRequest):
    """
    Downloads list of songs using spotdl via subprocess.Popen.
    Streams output logs to the client (NDJSON).
    Returns {"done": true, "session_id": "...", "download_url": "..."} at the end.
    """
    session_id = str(uuid.uuid4())
    logger.info(f"Starting batch download sesion (Stream): {session_id} for {len(request.urls)} songs")

    def event_generator():
        base_dir = os.getcwd()
        temp_dir = os.path.join(base_dir, "temp_downloads", session_id)
        os.makedirs(temp_dir, exist_ok=True)
        songs_file = os.path.join(temp_dir, "songs.txt")
        report_file = os.path.join(temp_dir, "downloadreport.txt")
        zip_filename = f"spotify_download_{session_id}"
        zip_path = os.path.join(base_dir, "temp_downloads", f"{zip_filename}.zip")
        
        try:
             # Helper to write to report
            def log_to_report(msg):
                with open(report_file, "a") as f:
                    f.write(msg + "\n")

            # Step B: Write songs.txt
            with open(songs_file, "w") as f:
                for url in request.urls:
                    f.write(url + "\n")
            
            init_msg = "Initialized download session..."
            yield json.dumps({"log": init_msg}) + "\n"
            log_to_report(init_msg)

            # Step C: Execute spotdl
            spotdl_bin = os.path.join(base_dir, "venv", "bin", "spotdl")
            if not os.path.exists(spotdl_bin):
                spotdl_bin = "spotdl"

            song_list = []
            with open(songs_file, "r") as f:
                 song_list = [line.strip() for line in f if line.strip()]

            cmd = [
                spotdl_bin,
                "download",
                *song_list,
                "--overwrite", "force",
                "--simple-tui"
            ]

            start_msg = f"Running spotdl for {len(song_list)} songs..."
            yield json.dumps({"log": start_msg}) + "\n"
            log_to_report(start_msg)
            
            # Use Popen to stream output
            process = subprocess.Popen(
                cmd,
                cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # Merge stderr into stdout
                text=True,
                bufsize=1 # Line buffered
            )
            
            # Read line by line
            total_songs = len(request.urls)
            songs_done = 0
            
            for line in process.stdout:
                line = line.strip()
                if line:
                    log_to_report(line)
                    
                    # Parse progress roughly
                    current_fraction = 0
                    if ": Downloading" in line:
                         current_fraction = 0.1
                    elif ": Embedding metadata" in line:
                         current_fraction = 0.5
                    elif ": Done" in line:
                         songs_done += 1
                         current_fraction = 0.0 # Song is done, waiting for next
                    
                    # Calculate total progress (avoid > 1.0)
                    overall_progress = min((songs_done + current_fraction) / total_songs, 0.99)
                    
                    yield json.dumps({"log": line, "progress_update": overall_progress}) + "\n"
            
            process.wait()
            
            if process.returncode != 0:
                 err_msg = f"Spotdl exited with code {process.returncode}"
                 log_to_report(err_msg)
                 yield json.dumps({"error": err_msg}) + "\n"
                 return

            # Step D: Verify & Package
            downloaded_files = [f for f in os.listdir(temp_dir) if f != "songs.txt" and f != "downloadreport.txt"]
            if not downloaded_files:
                 no_files_msg = "No files downloaded."
                 log_to_report(no_files_msg)
                 yield json.dumps({"error": no_files_msg}) + "\n"
                 return
                 
            zip_msg = "Zipping files..."
            yield json.dumps({"log": zip_msg}) + "\n"
            log_to_report(zip_msg)
            log_to_report("Download Report Complete.")
            
            shutil.make_archive(
                os.path.join(base_dir, "temp_downloads", zip_filename),
                'zip',
                temp_dir
            )
            
            download_url = f"/download_file/{session_id}"
            yield json.dumps({
                "done": True, 
                "session_id": session_id,
                "download_url": download_url,
                "log": "Download Complete!"
            }) + "\n"

        except Exception as e:
            logger.error(f"Stream Error: {e}")
            yield json.dumps({"error": str(e)}) + "\n"
            # Cleanup on error
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")
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
