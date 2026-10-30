"""
FastAPI main application — registers all routers and startup/shutdown events.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import check_database_connectivity, dispose_engine
from runtime_environment import RuntimeEnvironment
from services.market_data import market_data_service
from services.runtime.background_worker_lifecycle import BackgroundWorkerLifecycle
from services.trading.providers import (
    angel_master,
    market_snapshot_monitor,
    premarket_scheduler,
    prediction_outcome_monitor,
    risk_monitor,
)

from routers import market, signals, portfolio, news, trades, backtest, sectors, personal, trading, options, premarket, orb


runtime_environment = RuntimeEnvironment()
background_workers = BackgroundWorkerLifecycle(
    angel_master=angel_master,
    risk_monitor=risk_monitor,
    prediction_outcome_monitor=prediction_outcome_monitor,
    market_snapshot_monitor=market_snapshot_monitor,
    premarket_scheduler=premarket_scheduler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print("Starting AI Trading Research Platform...")
    workers_started = False
    if runtime_environment.should_start_background_workers:
        await background_workers.start()
        workers_started = True
        print("Background workers started")
    else:
        print("Skipping background workers (serverless runtime)")
    try:
        yield
    finally:
        try:
            if workers_started:
                await background_workers.stop()
        except Exception as exc:
            print(f"Background worker shutdown error: {type(exc).__name__}")
        try:
            await dispose_engine()
        except Exception as exc:
            print(f"Engine dispose error: {type(exc).__name__}")
        print("Shutting down...")


app = FastAPI(
    title="AI Trading Research Platform",
    description="Multi-agent AI platform for NSE/BSE market research and paper trading",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(market.router, prefix="/api/market", tags=["Market Data"])
app.include_router(signals.router, prefix="/api/signals", tags=["AI Signals"])
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(news.router, prefix="/api/news", tags=["News"])
app.include_router(trades.router, prefix="/api/trades", tags=["Trades"])
app.include_router(backtest.router, prefix="/api/backtest", tags=["Backtest"])
app.include_router(sectors.router, prefix="/api/sectors", tags=["Sectors"])
app.include_router(personal.router, prefix="/api/personal", tags=["Personal"])
app.include_router(trading.router, prefix="/api/trading", tags=["Trading"])
app.include_router(options.router, prefix="/api/options", tags=["Options"])
app.include_router(premarket.router, prefix="/api/premarket", tags=["Pre-Market"])
app.include_router(orb.router, prefix="/api/orb", tags=["ORB Strategy"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "platform": "AI Trading Research Platform"}


@app.get("/ready")
async def ready():
    try:
        await check_database_connectivity()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "database": "unavailable",
                "detail": type(exc).__name__,
            },
        )
    return {"status": "ready", "database": "ok"}


# ── WebSocket for live price streaming ─────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active_connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active_connections:
            self.active_connections.remove(ws)

    async def broadcast(self, data: dict):
        disconnected = []
        for ws in self.active_connections:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


manager = ConnectionManager()


@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Send live indices data every 5 seconds
            import asyncio
            await asyncio.sleep(5)
            indices = await market_data_service.fetch_index_quotes()
            await websocket.send_json({"type": "indices", "data": indices})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)
