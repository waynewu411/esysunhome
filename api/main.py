"""FastAPI application for ESY Sunhome API service."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta

from .client import (
    ESYSunhomeClient,
    get_session,
    create_session,
    remove_session,
    AuthenticationError,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Pydantic models
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_in: int
    device_id: Optional[str] = None
    device_sn: Optional[str] = None


class ModeRequest(BaseModel):
    mode: int  # 1=Regular, 2=Emergency, 3=Sell, 5=BEM


class ModeResponse(BaseModel):
    success: bool
    mode: int
    message: str


class DeviceInfo(BaseModel):
    device_id: Optional[str] = None
    device_sn: Optional[str] = None
    model: Optional[str] = None
    pv_power: Optional[int] = None
    rated_power: Optional[int] = None
    code: Optional[int] = None  # Current mode


class MqttCredentials(BaseModel):
    broker_url: str
    port: int
    username: str
    password: str
    use_tls: bool


class StatusResponse(BaseModel):
    timestamp: str
    battery: Optional[dict] = None
    solar: Optional[dict] = None
    grid: Optional[dict] = None
    load: Optional[dict] = None
    energy: Optional[dict] = None


# Session cache for status data
_status_cache = {}
_cache_ttl = timedelta(seconds=30)


def get_current_client(authorization: Optional[str] = Header(None)) -> ESYSunhomeClient:
    """Dependency to get current client from token."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    # Extract token from "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = parts[1]
    client = get_session(token)
    
    if not client:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    logger.info("ESY Sunhome API starting up...")
    yield
    logger.info("ESY Sunhome API shutting down...")
    # Cleanup sessions
    for token in list(get_session.__wrapped__.__globals__.get('_sessions', {}).keys()):
        remove_session(token)


app = FastAPI(
    title="ESY Sunhome API",
    description="REST API for ESY Sunhome battery systems",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate with ESY credentials and create a session."""
    try:
        client = ESYSunhomeClient(request.username, request.password)
        await client.authenticate()
        
        # Fetch device info
        try:
            await client.fetch_device()
        except Exception as e:
            logger.warning(f"Could not fetch device: {e}")
        
        # Create session
        token, _ = create_session(request.username, request.password)
        
        # Update client in session with authenticated client
        from .client import _sessions
        _sessions[token] = client
        
        return LoginResponse(
            token=token,
            expires_in=int(client.token_expiry.timestamp() - datetime.utcnow().timestamp()) if client.token_expiry else 3600,
            device_id=client.device_id,
            device_sn=client.device_sn,
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@app.post("/auth/logout")
async def logout(client: ESYSunhomeClient = Depends(get_current_client)):
    """Logout and close the session."""
    token = None
    from .client import _sessions
    for t, c in _sessions.items():
        if c is client:
            token = t
            break
    
    if token:
        remove_session(token)
    
    return {"success": True, "message": "Logged out"}


@app.get("/device", response_model=DeviceInfo)
async def get_device(client: ESYSunhomeClient = Depends(get_current_client)):
    """Get device information."""
    try:
        info = await client.get_device_info()
        return DeviceInfo(
            device_id=client.device_id,
            device_sn=client.device_sn or info.get("sn"),
            model=info.get("deviceTypeName"),
            pv_power=info.get("pvPower"),
            rated_power=info.get("ratedPower"),
            code=info.get("code"),
        )
    except Exception as e:
        logger.error(f"Get device error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status", response_model=StatusResponse)
async def get_status(client: ESYSunhomeClient = Depends(get_current_client)):
    """Get current battery status.
    
    This endpoint requests fresh data from the device and returns the status.
    For real-time streaming, use the MQTT credentials endpoint and connect to MQTT.
    """
    global _status_cache
    
    # Check cache
    cache_key = client.device_id
    if cache_key in _status_cache:
        cached_data, cached_time = _status_cache[cache_key]
        if datetime.utcnow() - cached_time < _cache_ttl:
            return cached_data
    
    try:
        # Request update
        await client.request_update()
        
        # Small delay to let data propagate
        await asyncio.sleep(1)
        
        # Get device info for current state
        info = await client.get_device_info()
        
        # Parse status from device info
        status = StatusResponse(
            timestamp=datetime.utcnow().isoformat() + "Z",
            battery={
                "soc": info.get("batterySoc"),
                "soh": info.get("batterySoh"),
                "voltage": info.get("batteryVoltage"),
                "current": info.get("batteryCurrent"),
                "power": info.get("batteryPower"),
                "temperature": info.get("batteryTemp"),
                "status": info.get("batteryStatus"),
            },
            solar={
                "pv_power": info.get("pvPower"),
                "pv1_voltage": info.get("pv1Voltage"),
                "pv1_current": info.get("pv1Current"),
                "pv2_voltage": info.get("pv2Voltage"),
                "pv2_current": info.get("pv2Current"),
            },
            grid={
                "power": info.get("gridPower"),
                "voltage": info.get("gridVoltage"),
                "frequency": info.get("gridFrequency"),
            },
            load={
                "power": info.get("loadPower"),
            },
            energy={
                "daily_generation": info.get("dailyPowerGeneration"),
                "daily_consumption": info.get("dailyPowerConsumption"),
                "daily_grid_import": info.get("dailyGridImport"),
                "daily_grid_export": info.get("dailyGridExport"),
                "total_generation": info.get("totalPowerGeneration"),
                "total_consumption": info.get("totalConsumption"),
            },
        )
        
        # Update cache
        _status_cache[cache_key] = (status, datetime.utcnow())
        
        return status
    except Exception as e:
        logger.error(f"Get status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/mode", response_model=ModeResponse)
async def set_mode(request: ModeRequest, client: ESYSunhomeClient = Depends(get_current_client)):
    """Set the operating mode.
    
    Mode codes:
    - 1: Regular Mode (normal self-consumption)
    - 2: Emergency Mode (charge from grid)
    - 3: Electricity Sell Mode (maximize grid export)
    - 5: Battery Energy Management (schedule mode)
    """
    valid_modes = [1, 2, 3, 5]
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid mode. Valid modes: {valid_modes}"
        )
    
    try:
        result = await client.set_mode(request.mode)
        return ModeResponse(
            success=True,
            mode=request.mode,
            message="Mode changed successfully"
        )
    except Exception as e:
        logger.error(f"Set mode error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mqtt/credentials", response_model=MqttCredentials)
async def get_mqtt_credentials(client: ESYSunhomeClient = Depends(get_current_client)):
    """Get MQTT credentials for real-time data streaming.
    
    Connect to the MQTT broker to receive real-time battery data.
    """
    try:
        creds = await client.get_mqtt_credentials()
        return MqttCredentials(
            broker_url=creds.broker_url,
            port=creds.port,
            username=creds.username,
            password=creds.password,
            use_tls=creds.use_tls,
        )
    except Exception as e:
        logger.error(f"Get MQTT credentials error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat() + "Z"}
