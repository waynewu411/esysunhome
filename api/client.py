"""Core ESY Sunhome API client - extracted from Home Assistant integration."""

import asyncio
import logging
import aiohttp
import os
from typing import Optional, Any, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta

ESY_API_BASE_URL = "http://esybackend.esysunhome.com:7073"
ESY_API_LOGIN_ENDPOINT = "/login?grant_type=app"
ESY_API_DEVICE_ENDPOINT = "/api/lsydevice/page?current=1&size=10"
ESY_API_OBTAIN_ENDPOINT = "/api/param/set/obtain?val=3&deviceId="
ESY_API_MODE_ENDPOINT = "/api/lsypattern/switch"
ESY_SCHEDULES_ENDPOINT = "/api/lsydevicechargedischarge/info?deviceId="
ESY_API_DEVICE_INFO = "/api/lsydevice/info"
ESY_API_CERT_ENDPOINT = "/security/cert/android"

ESY_MQTT_BROKER_URL = "abroadtcp.esysunhome.com"
ESY_MQTT_BROKER_PORT = 8883
ESY_MQTT_USERNAME = "admin"
ESY_MQTT_PASSWORD = "3omKSLaDI7q27OhX"

DEFAULT_PV_POWER = 6
DEFAULT_TP_TYPE = 1
DEFAULT_MCU_VERSION = 1049

_LOGGER = logging.getLogger(__name__)


@dataclass
class MqttCredentials:
    """Container for MQTT connection credentials and certificates."""
    broker_url: str
    port: int
    username: str
    password: str
    ca_cert_path: Optional[str] = None
    client_cert_path: Optional[str] = None
    client_key_path: Optional[str] = None
    use_tls: bool = True


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class ESYSunhomeClient:
    """Client for ESY Sunhome API."""
    
    def __init__(self, username: str, password: str, device_id: Optional[str] = None):
        self.username = username
        self.password = password
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.device_id: Optional[str] = device_id
        self.device_sn: Optional[str] = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _make_request(
        self,
        method: str,
        url: str,
        retry_auth: bool = True,
        **kwargs
    ) -> tuple[int, dict]:
        await self._ensure_token()
        
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"bearer {self.access_token}"
        
        session = await self._get_session()
        
        async with session.request(method, url, headers=headers, **kwargs) as response:
            status = response.status
            
            if status == 401 and retry_auth:
                _LOGGER.warning("Received 401, refreshing token")
                self.access_token = None
                await self._ensure_token()
                headers["Authorization"] = f"bearer {self.access_token}"
                async with session.request(method, url, headers=headers, **kwargs) as retry_response:
                    status = retry_response.status
                    try:
                        data = await retry_response.json()
                    except:
                        data = await retry_response.text()
                    return status, data
            
            try:
                data = await response.json()
            except:
                data = await response.text()
            
            return status, data

    async def _ensure_token(self):
        if self.is_token_expired() or not self.access_token:
            _LOGGER.info("Token expired or missing, authenticating")
            await self.authenticate()

    def is_token_expired(self) -> bool:
        if not self.token_expiry:
            return True
        return datetime.utcnow() >= (self.token_expiry - timedelta(seconds=60))

    async def authenticate(self):
        """Authenticate and retrieve bearer token."""
        url = f"{ESY_API_BASE_URL}{ESY_API_LOGIN_ENDPOINT}"
        headers = {"Content-Type": "application/json"}
        login_data = {
            "password": self.password,
            "clientId": "",
            "requestType": 1,
            "loginType": "PASSWORD",
            "userType": 2,
            "userName": self.username,
        }

        session = await self._get_session()
        async with session.post(url, json=login_data, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                self.access_token = data["data"].get("access_token")
                self.refresh_token = data["data"].get("refresh_token")
                expires_in = data["data"].get("expires_in", 0)
                self.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
                _LOGGER.info("Successfully authenticated")
            else:
                error_text = await response.text()
                raise AuthenticationError(f"Authentication failed: {response.status} - {error_text}")

    async def refresh_token(self) -> bool:
        """Refresh access token using refresh token."""
        if not self.refresh_token:
            return False

        url = f"{ESY_API_BASE_URL}/token"
        headers = {"Content-Type": "application/json"}
        refresh_data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }

        try:
            session = await self._get_session()
            async with session.post(url, json=refresh_data, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    self.access_token = data["data"].get("access_token")
                    self.refresh_token = data["data"].get("refresh_token")
                    expires_in = data["data"].get("expires_in", 0)
                    self.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
                    _LOGGER.info("Token refreshed successfully")
                    return True
                else:
                    return False
        except Exception as e:
            _LOGGER.error(f"Token refresh failed: {e}")
            return False

    async def fetch_device(self):
        """Fetch the device ID associated with the user."""
        url = f"{ESY_API_BASE_URL}{ESY_API_DEVICE_ENDPOINT}"
        
        status, data = await self._make_request("GET", url)
        
        if status == 200 and isinstance(data, dict) and "data" in data:
            self.device_id = data["data"]["records"][0]["id"]
            self.device_sn = data["data"]["records"][0].get("sn")
            _LOGGER.info(f"Device ID: {self.device_id}, SN: {self.device_sn}")
        else:
            raise Exception(f"Failed to fetch device: {data}")

    async def ensure_device(self):
        """Ensure we have device info."""
        if not self.device_id:
            await self.fetch_device()

    async def get_device_info(self) -> Dict[str, Any]:
        """Fetch detailed device info."""
        await self.ensure_device()
        
        url = f"{ESY_API_BASE_URL}{ESY_API_DEVICE_INFO}?id={self.device_id}"
        
        status, data = await self._make_request("GET", url)
        
        if status == 200 and isinstance(data, dict) and data.get("code") == 0:
            return data.get("data", {})
        else:
            raise Exception(f"Failed to fetch device info: {data}")

    async def request_update(self):
        """Request data update from the device."""
        await self.ensure_device()
        
        url = f"{ESY_API_BASE_URL}{ESY_API_OBTAIN_ENDPOINT}{self.device_id}"
        
        status, data = await self._make_request("GET", url)
        
        if status == 200:
            _LOGGER.debug("Data update requested")
        else:
            raise Exception(f"Failed to request update: {data}")

    async def set_mode(self, mode: int) -> Dict[str, Any]:
        """Set the operating mode.
        
        Modes:
        - 1: Regular Mode (normal self-consumption)
        - 2: Emergency Mode (charge from grid)
        - 3: Electricity Sell Mode (maximize grid export)
        - 5: Battery Energy Management (schedule mode)
        """
        await self.ensure_device()
        
        url = f"{ESY_API_BASE_URL}{ESY_API_MODE_ENDPOINT}"
        
        form_data = {
            "code": str(mode),
            "deviceId": self.device_id
        }
        
        status, data = await self._make_request("POST", url, data=form_data)
        
        if status == 200 and isinstance(data, dict):
            if data.get("code") == 0 or data.get("success"):
                _LOGGER.info(f"Mode successfully set to {mode}")
                return {"success": True, "mode": mode, "response": data}
            else:
                raise Exception(f"Mode change failed: {data.get('msg', 'Unknown error')}")
        else:
            raise Exception(f"Failed to set mode: {data}")

    async def get_mqtt_credentials(self, cert_dir: str = "/tmp/esy_certs") -> MqttCredentials:
        """Get MQTT credentials including certificates."""
        os.makedirs(cert_dir, exist_ok=True)
        
        try:
            device_info = await self.get_device_info()
            mqtt_username = device_info.get("mqttUserName", ESY_MQTT_USERNAME)
            mqtt_password = device_info.get("mqttPassword", ESY_MQTT_PASSWORD)
        except Exception as e:
            _LOGGER.warning(f"Using fallback MQTT credentials: {e}")
            mqtt_username = ESY_MQTT_USERNAME
            mqtt_password = ESY_MQTT_PASSWORD
        
        # Try to get certs
        try:
            url = f"{ESY_API_BASE_URL}{ESY_API_CERT_ENDPOINT}"
            status, data = await self._make_request("GET", url)
            
            if status == 200 and isinstance(data, dict) and data.get("code") == 0:
                cert_info = data.get("data", {})
                broker_url = cert_info.get("mqttDomain", ESY_MQTT_BROKER_URL)
                broker_port = cert_info.get("port", ESY_MQTT_BROKER_PORT)
                
                return MqttCredentials(
                    broker_url=broker_url,
                    port=broker_port,
                    username=mqtt_username,
                    password=mqtt_password,
                    use_tls=True
                )
        except Exception as e:
            _LOGGER.warning(f"Failed to get certs, using fallback: {e}")
        
        return MqttCredentials(
            broker_url=ESY_MQTT_BROKER_URL,
            port=ESY_MQTT_BROKER_PORT,
            username=mqtt_username,
            password=mqtt_password,
            use_tls=False
        )


# Session management for API
_sessions: Dict[str, ESYSunhomeClient] = {}


def get_session(token: str) -> Optional[ESYSunhomeClient]:
    """Get client by session token."""
    return _sessions.get(token)


def create_session(username: str, password: str) -> tuple[str, ESYSunhomeClient]:
    """Create a new session and return token and client."""
    import uuid
    token = str(uuid.uuid4())
    client = ESYSunhomeClient(username, password)
    _sessions[token] = client
    return token, client


def remove_session(token: str):
    """Remove a session."""
    if token in _sessions:
        client = _sessions.pop(token)
        asyncio.create_task(client.close())
