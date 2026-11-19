# AK DeviceLock REST API Documentation

Live JSON index: `GET /api/v1/docs/`

## Authentication
- **Device Registration**: `X-Enrollment-Key: <enrollment_key>`
- **Device Endpoints**: `Authorization: Device <device_token>` (SHA-256 hashed at rest; rotated via `/api/v1/devices/renew-token/`)
- **Operator Endpoints**: Authenticated Django staff session or HTTP Basic Auth

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/devices/register/` | `X-Enrollment-Key` | Register Device Owner device and issue device token |
| `POST` | `/api/v1/devices/sync/` | `Device` | Update device telemetry, `restriction_status`, and `last_seen` |
| `GET` | `/api/v1/devices/status/` | `Device` | Retrieve device registration and restriction state |
| `POST` | `/api/v1/devices/renew-token/` | `Device` | Rotate device-specific authentication token |
| `GET` | `/api/v1/commands/pending/` | `Device` | Fetch pending signed commands (`PENDING` -> `DELIVERED`, expires stale) |
| `POST` | `/api/v1/commands/acknowledge/` | `Device` | Report command execution (`EXECUTED` / `FAILED`); updates `restriction_status` only on `EXECUTED` |
| `GET` | `/api/v1/devices/{device_id}/` | `Operator` | Inspect device info and last command |
| `POST` | `/api/v1/devices/{device_id}/lock/` | `Operator` | Queue signed `DEVICE_LOCK` command |
| `POST` | `/api/v1/devices/{device_id}/unlock/` | `Operator` | Queue signed `DEVICE_UNLOCK` command |
| `POST` | `/api/v1/devices/{device_id}/release/` | `Operator` | Queue signed `DEVICE_RELEASE` command |
| `POST` | `/api/v1/devices/{device_id}/sync-command/` | `Operator` | Queue signed `DEVICE_SYNC` command |
| `GET` | `/api/v1/docs/` | Public | Machine-readable API endpoint index |

## Signed Command Format
Commands are signed with **ECDSA P-256 (`SHA256withECDSA`)** over the canonical UTF-8 string:
`command_id|device_id|command_type|issued_at|expires_at|nonce|reason`

