#!/bin/bash
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Function to kill processes on exit
cleanup() {
    echo "Stopping services..."
    kill $(jobs -p) 2>/dev/null
}
trap cleanup EXIT

echo "🚀 Starting Spotify Downloader..."

# Start Backend
echo "   --> Launching Backend (FastAPI)..."
cd backend
./venv/bin/uvicorn metadata_service:app --host 0.0.0.0 --port 8000 > ../backend.log 2>&1 &
cd ..
sleep 2 # Wait for backend to initialize

# Start Frontend
echo "   --> Launching Frontend (Streamlit)..."
cd frontend
./venv/bin/streamlit run app.py
