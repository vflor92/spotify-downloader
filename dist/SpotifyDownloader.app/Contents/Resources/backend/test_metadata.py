import requests
import sys

def test_analyze():
    url = "http://localhost:8000/analyze"
    # A short public playlist or single song for testing
    payload = {"url": "https://open.spotify.com/playlist/0aBO6YjdE8tAh6Try7eOpq"} 
    
    print(f"Testing {url} with payload {payload}...")
    try:
        response = requests.post(url, json=payload, timeout=30)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print("Response JSON:")
            print(data)
            if data['track_count'] > 0:
                print("SUCCESS: Retrieved tracks.")
            else:
                print("WARNING: Retrieved 0 tracks.")
        else:
            print(f"FAILED: {response.text}")
    except Exception as e:
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    test_analyze()
