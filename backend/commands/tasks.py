try:
    from celery import shared_task
except ImportError:
    def shared_task(fn):
        return fn

from commands.services import expire_stale
from notifications.services import notify_commands_available


@shared_task
def expire_stale_commands_task() -> int:
    expire_stale()
    return 1


@shared_task
def dispatch_command_notification_task(device_id: str) -> bool:
    from devices.models import Device

    device = Device.objects.filter(pk=device_id).first()
    if device is None:
        return False
    return notify_commands_available(device)
