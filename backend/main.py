import argparse
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import get_connection, init_db
from backend.services.tsv_importer import import_all, needs_import
from backend.routers import scripture, commentary, crosslinks, media, export


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    conn = get_connection()
    try:
        if needs_import(conn):
            print("First run: importing scripture data...", flush=True)
            import_all(conn)
        else:
            print("Scripture data already imported.", flush=True)
    finally:
        conn.close()
    yield
    # Shutdown (nothing to clean up)


app = FastAPI(title="Scripture Journal API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scripture.router, prefix="/api")
app.include_router(commentary.router, prefix="/api")
app.include_router(crosslinks.router, prefix="/api")
app.include_router(media.router, prefix="/api")
app.include_router(export.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
