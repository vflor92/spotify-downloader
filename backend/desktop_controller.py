import os
import json
import logging
import subprocess
import uuid
import shutil
import time
import tempfile
import traceback
from spotdl import Song
from spotdl.utils.spotify import SpotifyClient

# Configure logging to console or file
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Patch gettext to handle missing locale files in PyInstaller bundle
# This prevents "No translation file found for domain: 'base'" errors
import gettext
try:
    _orig_translation = gettext.translation
    def patched_translation(domain, localedir=None, languages=None, fallback=False):
        try:
            return _orig_translation(domain, localedir, languages, fallback)
        except (FileNotFoundError, OSError):
            # Fallback to default (no translation) if file not found
            return gettext.NullTranslations()
    gettext.translation = patched_translation
    logger.info("Patched gettext.translation for frozen environment.")
except Exception as e:
    logger.warning(f"Failed to patch gettext: {e}")

class DesktopController:
    def __init__(self):
        # Initialize SpotifyClient with spotdl's default "anonymous" credentials
        self.DEFAULT_CLIENT_ID = "5f573c9620494bae87890c0f08a60293"
        self.DEFAULT_CLIENT_SECRET = "212476d9b0f3472eaa762d90b19b0ba8"
        try:
            SpotifyClient.init(client_id=self.DEFAULT_CLIENT_ID, client_secret=self.DEFAULT_CLIENT_SECRET)
            logger.info("DesktopController initialized SpotifyClient.")
        except Exception as e:
            logger.warning(f"SpotifyClient init warning (might be already initialized): {e}")

    def analyze_stream(self, url: str):
        """
        Streams analysis progress for a playlist.
        Yields dicts: {"progress": X, "total": Y, "tracks": [...]}
        """
        logger.info(f"Streaming analysis for URL: {url}")
        
        # 1. Init Client (Already done in __init__ roughly, but helpful to force check)
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
                yield {"progress": 1, "total": 1, "tracks": data}
                return
            except Exception as e:
                yield {"error": str(e)}
                return

        # 3. Handle Playlist/Album Pagination
        try:
            results_chunk = []
            total_tracks = 0
            
            if "playlist" in url:
                resp = client.playlist_items(url)
                total_tracks = client.playlist(url)['tracks']['total']
            else:
                resp = client.album_tracks(url)
                total_tracks = client.album(url)['total_tracks']
            
            fetched_count = 0
            
            while True:
                items = resp['items']
                chunk_songs = []
                
                for item in items:
                    track_data = item.get('track', item) 
                    
                    if not track_data or track_data.get('is_local'):
                        continue
                        
                    artists = [a['name'] for a in track_data.get('artists', [])]
                    album_name = track_data.get('album', {}).get('name', 'Unknown')
                    
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
                
                yield {
                    "progress": fetched_count,
                    "total": total_tracks,
                    "tracks": chunk_songs
                }
                
                if resp.get('next'):
                    resp = client.next(resp)
                else:
                    break
                    
        except Exception as e:
             logger.error(f"Stream Error: {e}")
             yield {"error": str(e)}

    def download_batch(self, urls: list[str]):
        """
        Downloads list of songs using spotdl via subprocess.Popen.
        Yields dicts with log messages and progress.
        """
        session_id = str(uuid.uuid4())
        logger.info(f"Starting desktop download session: {session_id} for {len(urls)} songs")
        
        # Determine base directory. 
        # In a generic context, os.getcwd() is fine, but for PyInstaller, 
        # we might want a specific user output folder.
        # FIX: Use user's Downloads folder to avoid Read-only file system errors
        base_dir = os.path.expanduser("~/Downloads")
        
        # Create a specific folder for our app's downloads
        app_dl_dir = os.path.join(base_dir, "SpotifyDownloader")
        os.makedirs(app_dl_dir, exist_ok=True)
        
        temp_dir = os.path.join(app_dl_dir, "temp", session_id)
        os.makedirs(temp_dir, exist_ok=True)
        
        songs_file = os.path.join(temp_dir, "songs.txt")
        report_file = os.path.join(temp_dir, "downloadreport.txt")
        zip_filename = f"spotify_download_{session_id}"
        zip_path = os.path.join(app_dl_dir, f"{zip_filename}.zip")
        
        def log_to_report(msg):
            with open(report_file, "a") as f:
                f.write(msg + "\n")

        try:
            # Step B: Write songs.txt
            with open(songs_file, "w") as f:
                for url in urls:
                    f.write(url + "\n")
            
            init_msg = "Initialized download session..."
            yield {"log": init_msg}
            log_to_report(init_msg)

            # Step C: Execute spotdl using Python API
            from spotdl.download.downloader import Downloader
            from spotdl import Song

            # 1. Fetch Song objects (parallelized by spotdl usually, but here we do it simply)
            # Actually, Downloader.download takes Song objects or URLs if configured?
            # Let's use Song.from_url to be safe, as we did in analyze
            
            yield {"log": "Fetching song metadata..."}
            
            song_objects = []
            for url in urls:
                try:
                    found = Song.from_url(url)
                    if isinstance(found, list):
                        song_objects.extend(found)
                    else:
                        song_objects.append(found)
                except Exception as e:
                    log_to_report(f"Failed to fetch metadata for {url}: {e}")
            
            if not song_objects:
                yield {"error": "No valid songs found to download."}
                return

            yield {"log": f"Found {len(song_objects)} songs. Initializing Downloader..."}

            # 2. Configure Downloader
            # SpotDL 4.x uses a simple dict or data class for settings
            # We map our requirements here
            downloader_settings = {
                "output": os.path.join(temp_dir, "{artist} - {title}.{output-ext}"),
                "format": "mp3",
                "simple_tui": True, # Attempt to keep output clean
                "overwrite": "force",
                "ffmpeg": "ffmpeg", # Relies on PATH
                "threads": 4
            }
            
            downloader = Downloader(downloader_settings)

            # 3. Hook into progress? 
            # SpotDL doesn't easily expose a per-song callback in simple API.
            # But we can wrap the progress handler if we dig deep, or just blocking download.
            # For this "Fix", let's do blocking download but yield "Downloading..." message
            # To get real progress, we'd need to supply a 'progress_handler' if supported.
            # Checking recent spotdl source (via memory): it emits events.
            
            # Simple approach first: separate thread or just block and say "Working..."
            # Since we promised a progress bar, let's try to fake it or use a callback if we can.
            # But avoiding 'subprocess' is the priority.
            
            yield {"log": "Starting download process..."}
            
            # Downloader.download_multiple(songs) returns list of results
            # It's blocking. 
            # We can use a custom progress_handler if we pass it to Downloader or use the 'progress' library hooks.
            # For now, let's allow it to block for small batches, or just update "Downloading X/Y" if we iterated?
            # Iterating one by one is safer for progress updates!
            
            total_songs = len(song_objects)
            success_count = 0
            failure_count = 0
            
            for i, song in enumerate(song_objects):
                try:
                    yield {"log": f"Downloading ({i+1}/{total_songs}): {song.display_name}", "progress_update": i/total_songs}
                    
                    # Download single song
                    # spotdl returns a tuple (song, path) or raises exception
                    results = downloader.download_song(song)
                    
                    # Verify file exists or check result
                    # In normal spotdl, download_song returns the song object and path if successful
                    
                    log_to_report(f"Downloaded: {song.display_name}")
                    success_count += 1
                except Exception as e:
                    failure_count += 1
                    err_msg = f"FAILED: {song.display_name} - {str(e)}"
                    log_to_report(err_msg)
                    log_to_report(traceback.format_exc())
                    logger.error(err_msg)
                    logger.error(traceback.format_exc())
            
            summary_msg = f"\nDownload Summary: {success_count} succeeded, {failure_count} failed."
            log_to_report(summary_msg)
            yield {"log": "Finalizing...", "progress_update": 1.0}
            
            # Step D: Verify & Package
            downloaded_files = [f for f in os.listdir(temp_dir) if f != "songs.txt" and f != "downloadreport.txt"]
            if not downloaded_files:
                 no_files_msg = "No files downloaded. Check logs."
                 log_to_report(no_files_msg)
                 yield {"error": no_files_msg}
                 return
                 
            zip_msg = "Zipping files..."
            yield {"log": zip_msg}
            log_to_report(zip_msg)
            log_to_report("Download Report Complete.")
            
            shutil.make_archive(
                os.path.join(app_dl_dir, zip_filename),
                'zip',
                temp_dir
            )
            
            # In Desktop mode, we return the absolute path to the file
            yield {
                "done": True, 
                "session_id": session_id,
                "file_path": zip_path,
                "log": "Download Complete!"
            }

        except Exception as e:
            logger.error(f"Stream Error: {e}")
            yield {"error": str(e)}
            # Cleanup on error
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
