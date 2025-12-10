import streamlit as st
import pandas as pd
import requests
import json
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# Configuration
BACKEND_URL = "http://localhost:8000"

import os
# Use absolute path for dev mode, or relative for bundled mode
# Ideally we pass a PIL image or path.
icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "app_icon.jpg")

st.set_page_config(page_title="Spotify Downloader", page_icon=icon_path, layout="wide")

# UI Layout
col1, col2 = st.columns([1, 8])
with col1:
    if os.path.exists(icon_path):
        st.image(icon_path, width=80)
with col2:
    st.title("Spotify Downloader")

# --- Step A: Input ---
st.header("1. Analyze Playlist")
url_input = st.text_input("Spotify Playlist URL", placeholder="https://open.spotify.com/playlist/...")

# Import DesktopController directly (Monolith)
import sys
import os

# Ensure backend can be imported
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from backend.desktop_controller import DesktopController

# Initialize Controller
if 'controller' not in st.session_state:
    st.session_state.controller = DesktopController()

if "tracks_df" not in st.session_state:
    st.session_state["tracks_df"] = None

if "analyzed_data" not in st.session_state:
    st.session_state["analyzed_data"] = []

if st.button("Analyze Playlist"):
    if not url_input:
        st.error("Please enter a URL")
    else:

        # Progress Bar Container
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        all_tracks = []
        
        try:

             # Use the controller generator directly
            for chunk in st.session_state.controller.analyze_stream(url_input):
                if "error" in chunk:
                    st.error(f"Error: {chunk['error']}")
                    break
                
                if "tracks" in chunk:
                    # Append new tracks
                    if st.session_state['analyzed_data'] is None:
                         st.session_state['analyzed_data'] = []
                    st.session_state['analyzed_data'].extend(chunk['tracks'])
                    
                # Update progress
                if "progress" in chunk and "total" in chunk:
                    if chunk['total'] > 0:
                        pct = chunk['progress'] / chunk['total']
                        progress_bar.progress(min(pct, 1.0))
                    status_text.text(f"Fetched {chunk['progress']} / {chunk['total']} tracks...")
            
            if st.session_state['analyzed_data']:
                st.success(f"Analysis Complete! Found {len(st.session_state['analyzed_data'])} tracks.")
                status_text.empty()
                progress_bar.empty()
            else:
                st.warning("No tracks found.")


        except Exception as e:
            st.error(f"Connection Error: {e}")


# --- Step C: Display Grid & Select ---
if 'analyzed_data' in st.session_state and st.session_state['analyzed_data']:
    df = pd.DataFrame(st.session_state['analyzed_data'])
    
    # Add index for reference
    df.insert(0, 'No.', range(1, len(df) + 1))

    gb = GridOptionsBuilder.from_dataframe(df)
    # Enable filtering, sorting, and resizing by default
    gb.configure_default_column(filterable=True, sortable=True, resizable=True)
    
    gb.configure_selection('multiple', use_checkbox=True, groupSelectsChildren="GroupCheckboxSelectsChildren")
    gb.configure_column("No.", pinned="left", width=70)
    gb.configure_column("cover_url", hide=True)
    # gb.configure_column("url", hide=True) # Unhide URL based on user feedback
    
    # Fix selection bug
    gb.configure_grid_options(suppressRowClickSelection=True) 
    gb.configure_grid_options(rowMultiSelectWithClick=False) 

    grid_options = gb.build()
    
    st.write("### Select Songs to Download")
    grid_response = AgGrid(
        df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.MODEL_CHANGED,
        allow_unsafe_jscode=True,
        theme='streamlit'
    )
    
    selected_rows = grid_response['selected_rows']
    st.write(f"Selected: {len(selected_rows)} songs")
    
    # --- Step D: Download ---
    if st.button("Download Selected Songs"):
        if not selected_rows:
            st.warning("Please select at least one song.")
        else:
             # Extract URLs (handle dataframe dict vs object mismatch sometimes)
            urls = []
            if isinstance(selected_rows, pd.DataFrame):
                 urls = selected_rows['url'].tolist()
            else:
                 urls = [row['url'] for row in selected_rows]
                 
            dl_progress = st.progress(0)
            dl_status = st.empty()
            dl_log_expander = st.expander("Show detailed logs", expanded=True)
            dl_logs = st.empty()
            log_buffer = []

            try:
                # Use controller.download_batch generator
                for chunk in st.session_state.controller.download_batch(urls):
                    
                    # Error handling
                    if "error" in chunk:
                        st.error(f"Download Error: {chunk['error']}")
                        break
                    
                    # Log updates
                    if "log" in chunk:
                        msg = chunk['log']
                        log_buffer.append(msg)
                        dl_logs.code("\n".join(log_buffer[-10:]))
                        dl_status.text(msg)
                    
                    # Progress updates
                    if "progress_update" in chunk:
                        dl_progress.progress(chunk['progress_update'])

                    # Completion
                    if chunk.get("done") and "file_path" in chunk:
                        dl_progress.progress(1.0)
                        
                        file_path = chunk['file_path']
                        st.success(f"Download Complete! File saved to: {file_path}")
                        
                        # Read file for button
                        with open(file_path, "rb") as f:
                             bytes_data = f.read()
                        
                        st.download_button(
                            label="💾 Save Playlist ZIP",
                            data=bytes_data,
                            file_name="spotify_playlist.zip",
                            mime="application/zip"
                        )

            except Exception as e:
                st.error(f"Download Error: {e}")
