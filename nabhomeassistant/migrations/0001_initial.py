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
                ("base_url", models.TextField(default="", null=True)),
                ("access_token", models.TextField(default="", null=True)),
                ("json_data_base", models.TextField(default="", null=True)),
            ],
            options={
                "abstract": False,
            },
        ),
    ]
