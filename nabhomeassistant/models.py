from django.db import models

from nabcommon import singleton_model


class Config(singleton_model.SingletonModel):
    base_url = models.TextField(null=True, default="")
    access_token = models.TextField(null=True, default="")
    json_data_base = models.TextField(null=True, default="")
