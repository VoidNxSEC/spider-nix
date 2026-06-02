"""Spider-Nix Web GUI — FastAPI server."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from spider_nix.intel import (
    ApplicationTracker,
    AutoFillProfile,
    FormAutoFiller,
    JobSeekerProfile,
    JobStorage,
    match_jobs,
    scrape_all_boards,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Spider-Nix", version="0.3.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Default DB
DB_PATH = Path("jobs.db")

# ---------------------------------------------------------------------------
# Active hunt runs (in-memory)
# ---------------------------------------------------------------------------

active_runs: dict[str, dict[str, Any]] = {}


def _get_storage() -> JobStorage:
    return JobStorage(DB_PATH)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def page_hunt(request: Request):
    """Job Hunt page."""
    return templates.TemplateResponse("hunt.html", {"request": request})


@app.get("/pipeline", response_class=HTMLResponse)
async def page_pipeline(request: Request):
    """Pipeline tracking page."""
    return templates.TemplateResponse("pipeline.html", {"request": request})


@app.get("/autofill", response_class=HTMLResponse)
async def page_autofill(request: Request):
    """Auto-fill page."""
    return templates.TemplateResponse("autofill.html", {"request": request})


@app.get("/profile", response_class=HTMLResponse)
async def page_profile(request: Request):
    """Profile management page."""
    return templates.TemplateResponse("profile.html", {"request": request})


# ---------------------------------------------------------------------------
# API: Job Hunt
# ---------------------------------------------------------------------------


@app.post("/api/jobs/hunt")
async def api_hunt(data: dict):
    """Start a job hunt."""
    skills = data.get("skills", [])
    sources = data.get("sources", {})
    max_jobs = data.get("max_jobs", 50)

    run_id = f"hunt_{len(active_runs) + 1}"

    async def _run():
        active_runs[run_id] = {"status": "running", "jobs": [], "log": []}

        try:
            jobs = await scrape_all_boards(
                skills=skills if skills else None,
                max_per_source=max_jobs // 3,
                include_remoteok=sources.get("remoteok", True),
                include_wwr=sources.get("wwr", True),
                include_hn=sources.get("hn", True),
            )

            # Score with profile
            storage = _get_storage()
            profile = await storage.load_profile()
            if profile:
                jobs = match_jobs(jobs, profile, min_score=0)

            # Save to DB
            await storage.save_jobs_batch(jobs)

            active_runs[run_id] = {
                "status": "complete",
                "total": len(jobs),
                "jobs": [j.to_dict() for j in jobs[:50]],
            }
            await storage.close()
        except Exception as e:
            active_runs[run_id] = {"status": "error", "error": str(e)}

    asyncio.create_task(_run())
    return {"run_id": run_id, "status": "started"}


@app.get("/api/jobs/hunt/{run_id}/status")
async def api_hunt_status(run_id: str):
    """Check hunt status."""
    run = active_runs.get(run_id, {})
    return run


@app.get("/api/jobs/list")
async def api_jobs_list(
    source: str | None = None,
    min_score: float | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
):
    """List jobs with filters."""
    storage = _get_storage()
    try:
        if q:
            jobs = await storage.search_jobs(q, limit)
        else:
            jobs = await storage.get_jobs(min_score=min_score, limit=limit)
        return {"jobs": [j.to_dict() for j in jobs], "total": len(jobs)}
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# API: Pipeline
# ---------------------------------------------------------------------------


@app.get("/api/pipeline/stats")
async def api_pipeline_stats():
    """Get pipeline statistics."""
    storage = _get_storage()
    try:
        apps = await storage.get_applications(limit=200)
        stats = await storage.get_application_stats()
        return {"stats": stats, "applications": apps}
    finally:
        await storage.close()


@app.post("/api/jobs/{job_id}/status")
async def api_job_status(job_id: str, data: dict):
    """Update job application status."""
    storage = _get_storage()
    try:
        tracker = ApplicationTracker(storage)
        status = data.get("status", "saved")
        notes = data.get("notes", "")
        from spider_nix.intel.jobs import ApplicationStatus

        ok = await tracker.advance_status(job_id, ApplicationStatus(status), notes)
        return {"ok": ok}
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# API: Auto-fill
# ---------------------------------------------------------------------------


@app.post("/api/autofill/analyze")
async def api_autofill_analyze(data: dict):
    """Analyze a form URL and return fill data."""
    url = data.get("url", "")
    if not url:
        return JSONResponse({"error": "URL required"}, status_code=400)

    storage = _get_storage()
    try:
        # Load profile
        profile = await storage.load_profile()
        af_profile = AutoFillProfile()
        if profile:
            af_profile = AutoFillProfile(
                skills=profile.skills,
                desired_titles=profile.desired_titles,
            )

        # Analyze
        import httpx

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            html = resp.text

        filler = FormAutoFiller(af_profile)
        results = await filler.analyze_and_fill(url, html)
        return {"forms": results}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# API: Profile
# ---------------------------------------------------------------------------


@app.get("/api/profile")
async def api_profile_get():
    """Get current profile."""
    storage = _get_storage()
    try:
        profile = await storage.load_profile()
        if profile:
            return {"profile": profile.to_dict()}
        return {"profile": None}
    finally:
        await storage.close()


@app.put("/api/profile")
async def api_profile_update(data: dict):
    """Update profile."""
    storage = _get_storage()
    try:
        profile = JobSeekerProfile.from_dict(data)
        await storage.save_profile(profile)
        return {"ok": True}
    finally:
        await storage.close()


# ---------------------------------------------------------------------------
# WebSocket: Live updates
# ---------------------------------------------------------------------------


@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            action = msg.get("action", "")

            if action == "subscribe_hunt":
                run_id = msg.get("run_id", "")
                # Poll the run status and send updates
                for _ in range(60):  # 60 seconds max
                    run = active_runs.get(run_id, {})
                    await ws.send_json(run)
                    if run.get("status") in ("complete", "error"):
                        break
                    await asyncio.sleep(1)
            elif action == "ping":
                await ws.send_json({"pong": True})
    except WebSocketDisconnect:
        pass


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def start_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True):
    """Start the web server."""
    import uvicorn

    if open_browser:
        import webbrowser

        webbrowser.open(f"http://{host}:{port}")

    uvicorn.run(app, host=host, port=port, log_level="info")
