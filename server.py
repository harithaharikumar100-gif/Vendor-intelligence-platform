"""
server.py - DRiskify (NIVETA Platform) REST API Server
------------------------------------------------------
Serves endpoints for:
- POST /api/analyze: Runs SK-VDD-001 Due Diligence Pipeline
- POST /api/download-pdf: Generates and streams official SK-VDD-001 PDF report
- GET  /api/presets: Returns pre-configured enterprise targets
- GET  /api/health: Status check for AI & Serper APIs
- Serves static production build from frontend/dist (if built)
"""

import os
import io
import json
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any

from services import get_vendor_analysis
from normalizer import normalize_vendor_name
from pdf_generator import generate_pdf

app = FastAPI(
    title="DRiskify NIVETA Platform API",
    description="Skill SK-VDD-001: Vendor Intelligence Scraping for Due Diligence",
    version="1.0.0"
)

# Enable CORS for local React development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory analysis cache
ANALYSIS_CACHE = {}

# Pre-configured enterprise targets (Canadian & Global)
PRESETS = [
    {
        "name": "Shopify Inc.",
        "clean_name": "Shopify",
        "industry": "Technology & SaaS",
        "country": "Canada",
        "domain": "https://www.shopify.com",
        "ticker": "SHOP",
        "badge": "TSX: SHOP • Ottawa"
    },
    {
        "name": "BlackBerry Limited",
        "clean_name": "BlackBerry",
        "industry": "Technology & SaaS",
        "country": "Canada",
        "domain": "https://www.blackberry.com",
        "ticker": "BB",
        "badge": "TSX: BB • Waterloo"
    },
    {
        "name": "CGI Inc.",
        "clean_name": "CGI",
        "industry": "Technology & SaaS",
        "country": "Canada",
        "domain": "https://www.cgi.com",
        "ticker": "GIB.A",
        "badge": "TSX: GIB.A • Montreal"
    },
    {
        "name": "OpenText Corporation",
        "clean_name": "OpenText",
        "industry": "Technology & SaaS",
        "country": "Canada",
        "domain": "https://www.opentext.com",
        "ticker": "OTEX",
        "badge": "TSX: OTEX • Waterloo"
    },
    {
        "name": "Royal Bank of Canada (RBC)",
        "clean_name": "Royal Bank of Canada",
        "industry": "Banking, Financial & FinTech",
        "country": "Canada",
        "domain": "https://www.rbc.com",
        "ticker": "RY",
        "badge": "TSX: RY • Toronto"
    },
    {
        "name": "Constellation Software Inc.",
        "clean_name": "Constellation Software",
        "industry": "Technology & SaaS",
        "country": "Canada",
        "domain": "https://www.csisoftware.com",
        "ticker": "CSU",
        "badge": "TSX: CSU • Toronto"
    },
    {
        "name": "Thomson Reuters",
        "clean_name": "Thomson Reuters",
        "industry": "Telecommunications & Media",
        "country": "Canada",
        "domain": "https://www.thomsonreuters.com",
        "ticker": "TRI",
        "badge": "TSX: TRI • Toronto"
    },
    {
        "name": "Bombardier Inc.",
        "clean_name": "Bombardier",
        "industry": "Manufacturing & Supply Chain",
        "country": "Canada",
        "domain": "https://www.bombardier.com",
        "ticker": "BBD.B",
        "badge": "TSX: BBD.B • Montreal"
    }
]


class AnalyzeRequest(BaseModel):
    vendor: str
    industry: Optional[str] = "Technology & SaaS"
    country: Optional[str] = "Canada"
    concerns: Optional[str] = ""
    company_url: Optional[str] = ""
    business_number: Optional[str] = ""
    ticker: Optional[str] = ""


class PdfRequest(BaseModel):
    result: Dict[str, Any]
    vendor_name: Optional[str] = "Vendor Entity"


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "groq_configured": bool(os.getenv("GROQ_API_KEY")),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "serper_configured": bool(os.getenv("SERPER_API_KEY")),
        "skill_id": "SK-VDD-001",
        "platform": "DRiskify - NIVETA"
    }


@app.get("/api/presets")
def get_presets():
    return PRESETS


@app.post("/api/normalize")
def normalize_input(data: Dict[str, str]):
    vendor = data.get("vendor", "")
    return normalize_vendor_name(vendor)


@app.post("/api/analyze")
def analyze_vendor(req: AnalyzeRequest):
    if not req.vendor or not req.vendor.strip():
        raise HTTPException(status_code=400, detail="Vendor name is required.")

    norm = normalize_vendor_name(req.vendor)
    clean_name = norm["normalized_name"]

    cache_key = f"{clean_name}__{req.country}__{req.industry}__{req.ticker}__{req.company_url}"
    if cache_key in ANALYSIS_CACHE:
        print(f"⚡ Returning cached analysis for: {clean_name}")
        return ANALYSIS_CACHE[cache_key]

    result, raw_signals = get_vendor_analysis(
        vendor=clean_name,
        industry=req.industry or "Technology & SaaS",
        country=req.country or "Canada",
        concerns=req.concerns or "",
        company_url=req.company_url or "",
        business_number=req.business_number or "",
        ticker=req.ticker or ""
    )

    if "error" in result and not result.get("risk_scores"):
        raise HTTPException(status_code=500, detail=result["error"])

    ANALYSIS_CACHE[cache_key] = result
    return result


@app.post("/api/download-pdf")
def download_pdf(req: PdfRequest):
    try:
        vendor_name = req.vendor_name or req.result.get("vendor_name", "vendor")
        clean_filename = f"DRiskify_SK_VDD_001_{vendor_name.lower().replace(' ', '_')}.pdf"
        temp_pdf_path = os.path.join(os.getcwd(), clean_filename)

        generate_pdf(req.result, filename=temp_pdf_path, vendor_name=vendor_name)

        with open(temp_pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # Clean up temporary file
        if os.path.exists(temp_pdf_path):
            try:
                os.remove(temp_pdf_path)
            except Exception:
                pass

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{clean_filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF compilation failed: {e}")


# Serve frontend static build if present
dist_path = os.path.join(os.getcwd(), "frontend", "dist")
if os.path.exists(dist_path):
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting DRiskify NIVETA REST API on http://localhost:8000")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
