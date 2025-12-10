import PyInstaller.__main__
import os

# Build the macOS .app bundle
# Requires pyinstaller: pip install pyinstaller

print("Building SpotifyDownloader.app...")

PyInstaller.__main__.run([
    'run_app.py',
    '--name=SpotifyDownloader',
    '--windowed',
    '--onedir',
    '--icon=assets/icon.icns',
    '--clean',
    '--noconfirm',
    # Include FFmpeg binary (Source:Dest)
    '--add-binary=assets/bin/ffmpeg:assets/bin',
    # Include Source Code (Frontend & Backend) & Assets
    '--add-data=frontend:frontend',
    '--add-data=backend:backend',
    '--add-data=assets/app_icon.jpg:assets', # Fix: Explicitly bundle the icon image
    # Include hidden imports for spotdl and streamlit
    '--collect-all=spotdl',
    '--collect-all=streamlit',
    '--collect-all=st_aggrid',
    '--collect-all=pandas',
    '--collect-all=pykakasi',
    '--collect-all=yt_dlp',
    # Exclude unnecessary heavyweight stuff
    '--exclude-module=matplotlib',
    '--exclude-module=tkinter'
])

print("\n-----------------------------------------------------------")
print("Build Complete. Your app is in the 'dist' folder.")
print("Right-click 'dist/SpotifyDownloader.app' -> Open to run it.")
print("-----------------------------------------------------------")
