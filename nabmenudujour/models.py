from django.db import models

from nabcommon import singleton_model


class Config(singleton_model.SingletonModel):
    json_url = models.TextField(null=True, default="")
    next_performance_date = models.DateTimeField(null=True)
    next_performance_type = models.TextField(null=True)

    class Meta:
        app_label = "nabmenudujour"
