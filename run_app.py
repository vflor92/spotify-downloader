import sys
import os
import ffmpeg_setup
import streamlit.web.cli as stcli

def resolve_path(path):
    if getattr(sys, 'frozen', False):
        basedir = sys._MEIPASS
    else:
        basedir = os.path.dirname(__file__)
    return os.path.join(basedir, path)

if __name__ == "__main__":
    # 1. Setup FFmpeg first
    ffmpeg_setup.check_and_install_ffmpeg()

    # 2. Run Streamlit
    # We force the app to run in 'headless' mode so it doesn't pop up extra windows
    # developmentMode=false turns off the "Rerurn" buttons and internal errors
    sys.argv = [
        "streamlit",
        "run",
        resolve_path("frontend/app.py"),
        "--global.developmentMode=false", 
        "--server.headless=false"
    ]
    sys.exit(stcli.main())
