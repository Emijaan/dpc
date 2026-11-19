"""Notification channel. FCM is intentionally not enabled yet (no Firebase project).
The device polls /api/v1/commands/pending/. When FCM is added, send a data-only 'commands_available'
message here; the device must still fetch and verify the signed command from the backend."""


def notify_commands_available(device) -> bool:
    return False  # no-op until FCM is configured

