from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("commands", "0004_alter_devicecommand_command_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="devicecommand",
            name="command_type",
            field=models.CharField(
                choices=[
                    ("DEVICE_LOCK", "Lock"),
                    ("DEVICE_UNLOCK", "Unlock"),
                    ("DEVICE_STATUS", "Status"),
                    ("DEVICE_SYNC", "Sync"),
                    ("DEVICE_LOCATE", "Locate"),
                    ("DEVICE_PHOTO", "Capture Photo"),
                    ("DEVICE_CAMERA_OFF", "Camera Disable"),
                    ("DEVICE_CAMERA_ON", "Camera Enable"),
                    ("DEVICE_GPS_ON", "Gps Force On"),
                    ("DEVICE_GPS_UNLOCK", "Gps Unlock"),
                    ("DEVICE_NET_LOCK", "Network Restrict"),
                    ("DEVICE_NET_UNLOCK", "Network Allow"),
                    ("DEVICE_UPDATE", "Update Agent"),
                    ("DEVICE_RELEASE", "Release"),
                ],
                max_length=20,
            ),
        ),
    ]
