from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from commands.models import DeviceCommand
from commands.services import create_command, expire_stale
from devices.models import Device

ACTIONS = {
    "lock": DeviceCommand.Type.LOCK,
    "unlock": DeviceCommand.Type.UNLOCK,
    "sync": DeviceCommand.Type.SYNC,
}


@staff_member_required
def panel_home(request):
    rows = []
    for d in Device.objects.all().order_by("-last_seen"):
        expire_stale(d)
        last = d.commands.first()
        rows.append({"device": d, "online": d.is_online, "last": last})
    return render(request, "panel.html", {"rows": rows})


@staff_member_required
@require_POST
def panel_action(request, device_id, action):
    device = get_object_or_404(Device, pk=device_id)
    ctype = ACTIONS.get(action)
    if ctype and device.enrollment_status == Device.Enrollment.ENROLLED:
        busy = device.commands.filter(
            command_type=ctype,
            command_status__in=[DeviceCommand.Status.PENDING, DeviceCommand.Status.DELIVERED]).exists()
        if not busy:
            create_command(device, ctype, "operator panel")
    return redirect("panel")

