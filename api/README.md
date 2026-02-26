# ESY Sunhome API Service

A standalone REST API service for ESY Sunhome battery systems, extracted from the Home Assistant integration.

## Features

- 🔐 **Authentication** - Login with ESY app credentials
- 📊 **Device Info** - Get inverter details and status
- 🔋 **Status Monitoring** - Query battery, solar, grid, and load data
- 🎛️ **Mode Control** - Switch between operating modes (Regular, Emergency, Sell, BEM)
- 📡 **MQTT Credentials** - Get credentials for real-time data streaming

## Quick Start

### Install Dependencies

```bash
cd api
pip install -r requirements.txt
```

### Run the Server

```bash
python run_api.py --port 8000
```

Or with Docker:

```bash
docker-compose up -d
```

## API Endpoints

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | Login with ESY credentials |
| POST | `/auth/logout` | Logout and close session |

### Device

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/device` | Get device information |

### Status & Control

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | Get current battery status |
| POST | `/mode` | Set operating mode |
| GET | `/mqtt/credentials` | Get MQTT credentials for real-time streaming |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |

## Usage Examples

### Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "your@email.com", "password": "yourpassword"}'
```

Response:
```json
{
  "token": "abc123-...",
  "expires_in": 3600,
  "device_id": "123456",
  "device_sn": "SN123456789"
}
```

### Get Status

```bash
curl -X GET http://localhost:8000/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Set Mode

```bash
curl -X POST http://localhost:8000/mode \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode": 1}'
```

Mode codes:
- `1` - Regular Mode (normal self-consumption)
- `2` - Emergency Mode (charge from grid)
- `3` - Electricity Sell Mode (maximize grid export)
- `5` - Battery Energy Management (schedule mode)

### Get MQTT Credentials

```bash
curl -X GET http://localhost:8000/mqtt/credentials \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Use these credentials to connect to the MQTT broker for real-time data streaming.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| ESY_API_HOST | 0.0.0.0 | Host to bind to |
| ESY_API_PORT | 8000 | Port to bind to |

## Architecture

```
api/
├── __init__.py       # Package exports
├── client.py         # Core ESY API client (extracted from HA integration)
├── main.py           # FastAPI application
└── requirements.txt # Python dependencies
```

## License

MIT License - Same as the original Home Assistant integration.
