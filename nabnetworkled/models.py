from django.db import models

from nabcommon import singleton_model


class Config(singleton_model.SingletonModel):
    ok_color = models.CharField(default="#ff00ff", max_length=7)

    class Meta:
        app_label = "nabnetworkled"
