from django.urls import path

from .views import RFIDDataView, SoundSettingsView


urlpatterns = [
    path("", SoundSettingsView.as_view(), name="nabsound.settings"),
    path("rfid-data", RFIDDataView.as_view()),
]
