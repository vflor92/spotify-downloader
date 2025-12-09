import streamlit as st
import pandas as pd
import requests
import json
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode

# Configuration
BACKEND_URL = "http://localhost:8000"

st.set_page_config(page_title="Spotify Downloader", layout="wide")

st.title("Spotify Downloader")

# --- Step A: Input ---
st.header("1. Analyze Playlist")
url_input = st.text_input("Spotify Playlist URL", placeholder="https://open.spotify.com/playlist/...")

if "tracks_df" not in st.session_state:
    st.session_state["tracks_df"] = None

if st.button("Analyze Playlist"):
    if not url_input:
        st.error("Please enter a URL")
    else:

        # Progress Bar Container
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        all_tracks = []
        
        try:
            # Use GET for streaming endpoint
            with requests.get(f"{BACKEND_URL}/analyze_stream", params={"url": url_input}, stream=True) as response:
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            json_data = line.decode('utf-8')
                            try:
                                chunk = json.loads(json_data)
                                
                                if "error" in chunk:
                                    st.error(f"Error: {chunk['error']}")
                                    break
                                    
                                # Update data
                                tracks_chunk = chunk.get("tracks", [])
                                all_tracks.extend(tracks_chunk)
                                
                                # Update UI
                                progress = chunk.get("progress", 0)
                                total = chunk.get("total", 1)
                                if total > 0:
                                    percentage = min(progress / total, 1.0)
                                    progress_bar.progress(percentage)
                                    status_text.text(f"Fetched {progress} / {total} songs...")
                                    
                            except json.JSONDecodeError:
                                continue
                                
                    # Finalization
                    if all_tracks:
                        st.session_state["tracks_df"] = pd.DataFrame(all_tracks)
                        st.success(f"Analysis Complete! Found {len(all_tracks)} tracks.")
                        status_text.empty()
                        progress_bar.empty()
                    else:
                        st.warning("No tracks found.")
                        
                else:
                    st.error(f"Server Error: {response.text}")

        except Exception as e:
            st.error(f"Connection Error: {e}")

# --- Step C: Display & Select (The Grid) ---
if st.session_state["tracks_df"] is not None:
    st.header("2. Select Songs")
    
    df = st.session_state["tracks_df"]
    
    # Add Index Column (1-based) if not already present
    if "No." not in df.columns:
        df.insert(0, "No.", range(1, len(df) + 1))
    
    # Configure AgGrid
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_column("No.", pinned=True, width=70) # Pin index to left
    # gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=20) # Disable pagination to allow scrolling
    gb.configure_side_bar() # Enable sidebar filters
    gb.configure_default_column(groupable=True, value=True, enableRowGroup=True, aggFunc='sum', editable=False)
    
    # Selection Configuration
    # Pre-select all rows by default
    gb.configure_selection(
        'multiple', 
        use_checkbox=True, 
        groupSelectsChildren=True, 
        groupSelectsFiltered=True,
        pre_selected_rows=list(range(len(df))),
        suppressRowClickSelection=True, 
        rowMultiSelectWithClick=False
    )
    
    # Select All by default logic would typically be handling via pre_selected_rows if needed
    # st_aggrid doesn't straightforwardly support "pre-select all" via GridOptions easily without passing selected rows
    # For now, we rely on the "Select All" checkbox in the header which is enabled by 'multiple' + checkbox
    
    gridOptions = gb.build()
    
    grid_response = AgGrid(
        df,
        gridOptions=gridOptions,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        fit_columns_on_grid_load=True,
        theme='streamlit', 
        height=400,
        allow_unsafe_jscode=True
    )
    
    selected_rows = grid_response['selected_rows']
    
    st.write(f"Selected {len(selected_rows)} songs")

    # --- Step D: Download ---
    st.header("3. Download")
    
    if st.button("Download Selected Songs"):
        if not selected_rows:
            st.warning("Please select at least one song.")
        else:
            # selected_rows is a list of dicts, but might be a pandas df depending on return mode
            # st_aggrid returns list of dicts mostly
            
            # Extract URLs
            # Handle potential difference in return format (sometimes it's a DataFrame)
            if isinstance(selected_rows, pd.DataFrame):
                 urls = selected_rows['url'].tolist()
            else:
                 urls = [row['url'] for row in selected_rows]
                 
            with st.spinner("Processing Download (this may take a while)..."):
                try:
                    # Calling the backend endpoint
                    # This is a blocking call!
                    dl_response = requests.post(f"{BACKEND_URL}/download_batch", json={"urls": urls}, stream=False)
                    
                    if dl_response.status_code == 200:
                        st.session_state['download_content'] = dl_response.content
                        st.success("Download ready! Click below to save.")
                    else:
                        st.error(f"Download failed: {dl_response.text}")
                except Exception as e:
                    st.error(f"Connection Error: {e}")

    # Show download button if content exists
    if 'download_content' in st.session_state:
        st.download_button(
            label="💾 Save Playlist ZIP",
            data=st.session_state['download_content'],
            file_name="spotify_playlist.zip",
            mime="application/zip"
        )
