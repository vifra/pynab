from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nabweatherd", "0014_alter_config_location"),
    ]

    operations = [
        migrations.AddField(
            model_name="config",
            name="weather_animations",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
