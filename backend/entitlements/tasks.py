try:
    from celery import shared_task
except ImportError:
    def shared_task(fn):
        return fn

from entitlements.services import expire_stale_allocations


@shared_task
def expire_stale_allocations_task() -> int:
    return expire_stale_allocations()
