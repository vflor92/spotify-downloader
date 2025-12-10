import requests
import os

def test_download():
    url = "http://localhost:8000/download_batch"
    # Use a very short song/sound effect to make the test fast
    # This is a random short sound effect on Spotify or a popular song
    payload = {"urls": ["https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"]} # Never Gonna Give You Up (Classic)
    
    print(f"Testing {url} with payload {payload}...")
    try:
        response = requests.post(url, json=payload, stream=True)
        
        if response.status_code == 200:
            content_type = response.headers.get("content-type")
            print(f"SUCCESS: Received response with Content-Type: {content_type}")
            
            filename = "test_download.zip"
            with open(filename, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = os.path.getsize(filename)
            print(f"Saved {filename} ({file_size} bytes)")
            
            if file_size > 1000:
                print("PASS: File size looks reasonable (contains audio/zip data).")
            else:
                print("FAIL: File is too small to be a valid zip of a song.")
        else:
            print(f"FAIL: Status Code {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_download()
