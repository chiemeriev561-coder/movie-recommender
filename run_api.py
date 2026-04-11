#!/usr/bin/env python3
"""
Startup script for the Movie Recommender API
"""

import uvicorn
import sys
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def main():
    """Run the Movie Recommender API server."""
    
    # Check if virtual environment is activated
    if "VIRTUAL_ENV" not in os.environ:
        print("Warning: Virtual environment not detected.")
    
    # Configuration from environment variables
    PORT = int(os.getenv("PORT", "8000"))
    HOST = os.getenv("HOST", "0.0.0.0")
    RELOAD = os.getenv("RELOAD", "false").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "info").lower()
    
    print(f"Starting Movie Recommender API on {HOST}:{PORT} (reload={RELOAD})...")
    print(f"API Documentation: http://{HOST if HOST != '0.0.0.0' else 'localhost'}:{PORT}/docs")
    print(f"Health Check: http://{HOST if HOST != '0.0.0.0' else 'localhost'}:{PORT}/api/health")
    print("\nPress Ctrl+C to stop the server\n")
    
    # Run the API server
    uvicorn.run(
        "api:app",
        host=HOST,
        port=PORT,
        reload=RELOAD,
        log_level=LOG_LEVEL
    )

if __name__ == "__main__":
    main()
