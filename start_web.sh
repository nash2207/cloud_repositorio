#!/bin/bash
# Start Web Interface for Slice Manager

echo "🚀 Starting Slice Manager Web Interface..."

# Check if running in virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Warning: No virtual environment detected"
    echo "   Consider using: python3 -m venv venv && source venv/bin/activate"
fi

# Check dependencies
echo "📦 Checking dependencies..."
python3 -c "import fastapi, uvicorn, yaml" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ Missing dependencies. Installing..."
    pip3 install -r requirements.txt
fi

# Start web server
echo "🌐 Starting server on http://0.0.0.0:8080"
echo "   Access from browser: http://server4_ip:8080"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python3 web_api.py
