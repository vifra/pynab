from django.urls import path

from . import views
from .views import RFIDDataView, SettingsView

urlpatterns = [
    path("settings", SettingsView.as_view()),
    path("test-connection", views.test_connection),
    path("entities", views.entities),
    path("preview-state", views.preview_state),
    path("rfid-data", RFIDDataView.as_view()),
]
