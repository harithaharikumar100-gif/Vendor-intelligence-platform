"""
run_platform.py - Unified Launcher for DRiskify NIVETA Platform
----------------------------------------------------------------
Usage:
  python run_platform.py
"""

import os
import sys
import subprocess
import time
import webbrowser

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")


def main():
    print("==========================================================")
    print("🛡️  DRiskify — NIVETA Platform (Skill SK-VDD-001)")
    print("==========================================================")

    # 1. Check if frontend node_modules exist
    node_modules = os.path.join(FRONTEND_DIR, "node_modules")
    if not os.path.exists(node_modules):
        print("\n📦 Installing React frontend dependencies (npm install)...")
        subprocess.run("npm install", cwd=FRONTEND_DIR, shell=True, check=True)

    # 2. Build the production React frontend
    dist_dir = os.path.join(FRONTEND_DIR, "dist")
    if not os.path.exists(dist_dir):
        print("\n⚡ Building React production bundle (npm run build)...")
        subprocess.run("npm run build", cwd=FRONTEND_DIR, shell=True, check=True)

    print("\n🚀 Launching DRiskify FastAPI Server on http://localhost:8000 ...")
    print("📄 Open your browser to http://localhost:8000 to access the platform.")
    
    time.sleep(1)
    webbrowser.open("http://localhost:8000")

    # Run FastAPI server via Uvicorn
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
