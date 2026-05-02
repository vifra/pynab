from django.urls import path

from .views import SoundSettingsView


urlpatterns = [
    path("", SoundSettingsView.as_view(), name="nabsound.settings"),
]
