import os
import sys

def check_and_install_ffmpeg():
    """
    Checks if FFmpeg is available.
    In the bundled app, it should be in sys._MEIPASS/assets/bin/ffmpeg.
    We add that folder to PATH.
    """
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        bundle_dir = sys._MEIPASS
        ffmpeg_bin_dir = os.path.join(bundle_dir, "assets", "bin")
        ffmpeg_path = os.path.join(ffmpeg_bin_dir, "ffmpeg")
        
        if os.path.exists(ffmpeg_path):
            # Ensure executable permission (restore 0o755)
            # Sometimes entitlements strip this upon copying
            try:
                os.chmod(ffmpeg_path, 0o755)
            except Exception as e:
                print(f"Warning: Could not chmod ffmpeg: {e}")

            # Add to PATH
            os.environ["PATH"] += os.pathsep + ffmpeg_bin_dir
            print(f"FFmpeg configured at: {ffmpeg_path}")
        else:
            print("Error: FFmpeg binary missing from bundle.")
    else:
        # Development mode
        # Assume it's in local assets/bin or already installed globally
        local_bin = os.path.join(os.getcwd(), "assets", "bin")
        if os.path.exists(local_bin):
            os.environ["PATH"] += os.pathsep + local_bin
            print(f"Dev Mode: Added {local_bin} to PATH")
