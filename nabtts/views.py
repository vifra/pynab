import datetime

from django.http import JsonResponse, QueryDict
from django.shortcuts import render
from django.views.generic import TemplateView

from . import rfid_data
from .models import Config
from .nabtts import NabTTS
from .tts import (
    EDGE_VOICE_CHOICES,
    GOOGLE_VOICE_CHOICES,
    PROVIDER_CHOICES,
    STYLE_CHOICES,
    VOICE_CHOICES,
)


class SettingsView(TemplateView):
    template_name = "nabtts/settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["config"] = Config.load()
        context["provider_choices"] = PROVIDER_CHOICES
        context["voice_choices"] = VOICE_CHOICES
        context["edge_voice_values"] = [value for value, label in EDGE_VOICE_CHOICES]
        context["google_voice_values"] = [
            value for value, label in GOOGLE_VOICE_CHOICES
        ]
        context["style_choices"] = STYLE_CHOICES
        return context

    def get(self, request, *args, **kwargs):
        return render(
            request,
            SettingsView.template_name,
            context=self.get_context_data(**kwargs),
        )

    def put(self, request, *args, **kwargs):
        put_dict = QueryDict(request.body, encoding=request._encoding)
        payload = rfid_data.normalize_payload(
            {
                "text": put_dict.get("text", ""),
                "provider": put_dict.get("provider", ""),
                "voice": put_dict.get("voice", ""),
                "style": put_dict.get("style", ""),
            }
        )
        if not payload["text"]:
            return JsonResponse(
                {"status": "error", "message": "Message vide."},
                status=400,
            )
        config = Config.load()
        config.next_performance_date = datetime.datetime.now(
            datetime.timezone.utc
        )
        config.next_performance_text = rfid_data.serialize_payload(
            payload["text"],
            payload["voice"],
            payload["style"],
            payload["provider"],
        )
        config.save()
        NabTTS.signal_daemon()
        return JsonResponse({"status": "ok"})


class RFIDDataView(TemplateView):
    template_name = "nabtts/rfid-data.html"

    def get(self, request, *args, **kwargs):
        uid = request.GET.get("uid", "")
        payload = rfid_data.read_data_ui_for_views(uid)
        if not payload["text"]:
            tag_text = rfid_data.unserialize(request.GET.get("data", ""))
            if tag_text != rfid_data.DATA_IN_LOCAL_DB:
                payload = rfid_data.unserialize_payload(tag_text)
        return render(
            request,
            RFIDDataView.template_name,
            context={
                "tts_text": payload["text"],
                "tts_provider": payload["provider"],
                "tts_voice": payload["voice"],
                "tts_style": payload["style"],
                "tts_uid": uid,
                "provider_choices": PROVIDER_CHOICES,
                "voice_choices": VOICE_CHOICES,
                "edge_voice_values": [
                    value for value, label in EDGE_VOICE_CHOICES
                ],
                "google_voice_values": [
                    value for value, label in GOOGLE_VOICE_CHOICES
                ],
                "style_choices": STYLE_CHOICES,
            },
        )

    def post(self, request, *args, **kwargs):
        uid = request.POST.get("tts_uid", "")
        payload = rfid_data.normalize_payload(
            {
                "text": request.POST.get("tts_text", ""),
                "provider": request.POST.get("tts_provider", ""),
                "voice": request.POST.get("tts_voice", ""),
                "style": request.POST.get("tts_style", ""),
            }
        )
        rfid_data.write_data_ui_for_views(
            uid,
            payload["text"],
            payload["voice"],
            payload["style"],
            payload["provider"],
        )
        return JsonResponse({"data": rfid_data.DATA_IN_LOCAL_DB})
