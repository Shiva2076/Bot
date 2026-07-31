"""
FastAPI main application — registers all routers and startup/shutdown events.
"""
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from database import create_tables
from config import settings
from services.market_data import market_data_service

from routers import market, signals, portfolio, news, trades, backtest, sectors


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print("Starting AI Trading Research Platform...")
    await create_tables()
    print("Database tables created")
    yield
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


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "platform": "AI Trading Research Platform"}


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
