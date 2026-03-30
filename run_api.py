#!/usr/bin/env python3
"""
Startup script for the Movie Recommender API
"""

import uvicorn
import sys
import os

def main():
    """Run the Movie Recommender API server."""
    
    # Check if virtual environment is activated
    if "VIRTUAL_ENV" not in os.environ:
        print("Warning: Virtual environment not detected.")
        print("Please activate the virtual environment first:")
        print("source venv/bin/activate")
        sys.exit(1)
    
    print("Starting Movie Recommender API...")
    print("API Documentation: http://localhost:8000/docs")
    print("Alternative Documentation: http://localhost:8000/redoc")
    print("Health Check: http://localhost:8000/api/health")
    print("\nPress Ctrl+C to stop the server\n")
    
    # Run the API server
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()
