from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Config",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("json_data_base", models.TextField(default="", null=True)),
                ("next_performance_date", models.DateTimeField(null=True)),
                (
                    "next_performance_text",
                    models.TextField(default="", null=True),
                ),
            ],
            options={
                "app_label": "nabtts",
            },
        ),
    ]
