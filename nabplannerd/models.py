from django.db import models


def all_weekdays():
    return [0, 1, 2, 3, 4, 5, 6]


class ScheduledRule(models.Model):
    MODE_TIMES = "times"
    MODE_INTERVAL = "interval"
    MODE_WINDOW = "window"

    name = models.TextField(default="")
    service = models.TextField(default="")
    action = models.TextField(default="")
    color = models.TextField(default="")
    enabled = models.BooleanField(default=True)
    mode = models.TextField(default=MODE_TIMES)
    weekdays = models.JSONField(default=all_weekdays)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    trigger_times = models.JSONField(default=list)
    interval_minutes = models.IntegerField(null=True, blank=True)
    last_triggered_key = models.TextField(null=True, blank=True)

    class Meta:
        app_label = "nabplannerd"
        ordering = ["service", "name", "id"]
