import streamlit as st
import pandas as pd
import requests
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
        with st.spinner("Analyzing playlist..."):
            try:
                response = requests.post(f"{BACKEND_URL}/analyze", json={"url": url_input})
                if response.status_code == 200:
                    data = response.json()
                    tracks = data.get("tracks", [])
                    if tracks:
                        st.session_state["tracks_df"] = pd.DataFrame(tracks)
                        st.success(f"Found {len(tracks)} tracks!")
                    else:
                        st.warning("No tracks found.")
                else:
                    st.error(f"Error: {response.text}")
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
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=20)
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
                 
            with st.spinner("Initiating download batch..."):
                try:
                    # Calling the backend endpoint
                    dl_response = requests.post(f"{BACKEND_URL}/download_batch", json={"urls": urls})
                    
                    if dl_response.status_code == 200:
                        st.success("Download started! (Mock mocked for now)")
                        # In real scenario, we would stream the zip file here
                    else:
                        st.error(f"Download failed: {dl_response.text}")
                        
                except Exception as e:
                     st.error(f"Error contacting backend: {e}")
