from django.db import models

from nabcommon import singleton_model


class Config(singleton_model.SingletonModel):
    json_data_base = models.TextField(null=True, default="")
    next_performance_date = models.DateTimeField(null=True)
    next_performance_text = models.TextField(null=True, default="")

    class Meta:
        app_label = "nabtts"
