from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("devices", "0005_device_dealer_company_device_dealer_mobile_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="device",
            name="camera_disabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="device",
            name="gps_forced_on",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="device",
            name="ip_address",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="device",
            name="last_latitude",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="device",
            name="last_location_accuracy",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="device",
            name="last_location_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="device",
            name="last_longitude",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="device",
            name="last_photo_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="device",
            name="last_photo_b64",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="device",
            name="network_operator",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="device",
            name="network_restricted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="device",
            name="network_type",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="device",
            name="wifi_ssid",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
