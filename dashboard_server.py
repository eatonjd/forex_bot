"""
Streamlit Dashboard Server for Cloud Run

Wraps the Streamlit dashboard for deployment to Cloud Run.
Configures Streamlit to run on port 8080 with proper settings.
"""

import os
import sys

if __name__ == "__main__":
    # Set Streamlit configuration via sys.argv
    sys.argv = [
        "streamlit",
        "run",
        "dashboard.py",
        "--server.port=8080",
        "--server.address=0.0.0.0",
        "--server.headless=true",
        "--server.enableCORS=false",
        "--server.enableXsrfProtection=false",
    ]

    # Import and run Streamlit CLI
    from streamlit.web import cli as stcli

    sys.exit(stcli.main())
