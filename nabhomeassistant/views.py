import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import TemplateView
import requests

from . import rfid_data
from .models import Config
from .nabhomeassistant import (
    NabHomeAssistant,
    apply_speech_rewrite,
    home_assistant_state_text,
)


def _home_assistant_connection_data():
    config = Config.load()
    base_url = (config.base_url or "").rstrip("/")
    access_token = config.access_token or ""
    headers = {"Authorization": f"Bearer {access_token}"}
    return base_url, access_token, headers


def _home_assistant_error_response(error, status=502):
    if isinstance(error, requests.exceptions.HTTPError):
        status_code = (
            error.response.status_code if error.response is not None else None
        )
        if status_code in (401, 403):
            message = "Jeton d'acces refuse par Home Assistant."
        elif status_code == 404:
            message = "Adresse Home Assistant incorrecte."
        else:
            message = "Home Assistant a renvoye une erreur."
        return JsonResponse(
            {
                "status": "error",
                "message": message,
                "http_status": status_code,
            },
            status=status,
        )
    if isinstance(error, requests.exceptions.Timeout):
        message = "Home Assistant ne repond pas assez vite."
    elif isinstance(error, requests.exceptions.RequestException):
        message = "Impossible de joindre Home Assistant."
    else:
        message = "Reponse Home Assistant invalide."
    return JsonResponse({"status": "error", "message": message}, status=status)


class SettingsView(TemplateView):
    template_name = "nabhomeassistant/settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["config"] = Config.load()
        return context

    def post(self, request, *args, **kwargs):
        config = Config.load()
        if "base_url" in request.POST:
            config.base_url = request.POST["base_url"].strip()
        if "access_token" in request.POST:
            config.access_token = request.POST["access_token"].strip()
        config.save()
        NabHomeAssistant.signal_daemon()
        context = self.get_context_data(**kwargs)
        return render(request, SettingsView.template_name, context=context)


def test_connection(request):
    base_url, access_token, headers = _home_assistant_connection_data()
    if not base_url or not access_token:
        return JsonResponse(
            {
                "status": "error",
                "message": "Adresse Home Assistant ou jeton d'acces manquant.",
            },
            status=400,
        )
    try:
        response = requests.get(f"{base_url}/api/", headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as error:
        return _home_assistant_error_response(error)
    return JsonResponse(
        {
            "status": "ok",
            "message": "Connexion Home Assistant reussie.",
        }
    )


def entities(request):
    base_url, access_token, headers = _home_assistant_connection_data()
    if not base_url or not access_token:
        return JsonResponse(
            {
                "status": "error",
                "message": "Adresse Home Assistant ou jeton d'acces manquant.",
            },
            status=400,
        )
    try:
        response = requests.get(
            f"{base_url}/api/states", headers=headers, timeout=10
        )
        response.raise_for_status()
        states = response.json()
        if not isinstance(states, list):
            raise ValueError("Home Assistant returned a non-list states value")
    except Exception as error:
        return _home_assistant_error_response(error)

    readable_entities = []
    for state in states:
        if not isinstance(state, dict):
            continue
        entity_id = state.get("entity_id")
        if not entity_id:
            continue
        attributes = state.get("attributes", {})
        if not isinstance(attributes, dict):
            attributes = {}
        readable_entities.append(
            {
                "entity_id": entity_id,
                "name": attributes.get("friendly_name") or entity_id,
                "state": state.get("state", ""),
                "unit": attributes.get("unit_of_measurement") or "",
            }
        )
    readable_entities.sort(key=lambda entity: entity["entity_id"])
    return JsonResponse({"status": "ok", "entities": readable_entities})


def preview_state(request):
    entity_id = request.GET.get("entity_id", "").strip()
    if not entity_id:
        return JsonResponse(
            {"status": "error", "message": "Entite Home Assistant manquante."},
            status=400,
        )

    base_url, access_token, headers = _home_assistant_connection_data()
    if not base_url or not access_token:
        return JsonResponse(
            {
                "status": "error",
                "message": "Adresse Home Assistant ou jeton d'acces manquant.",
            },
            status=400,
        )
    try:
        response = requests.get(
            f"{base_url}/api/states/{entity_id}", headers=headers, timeout=10
        )
        response.raise_for_status()
        state = response.json()
        if not isinstance(state, dict):
            raise ValueError("Home Assistant returned a non-object state")
    except Exception as error:
        return _home_assistant_error_response(error)

    attributes = state.get("attributes", {})
    if not isinstance(attributes, dict):
        attributes = {}
    value = state.get("state", "")
    unit = attributes.get("unit_of_measurement") or ""
    display_value = f"{value} {unit}" if unit else value
    spoken_text = home_assistant_state_text(entity_id, state)
    action = {
        "speech_regex": request.GET.get("speech_regex", ""),
        "speech_replacement": request.GET.get("speech_replacement", ""),
    }
    spoken_text = apply_speech_rewrite(action, spoken_text)
    return JsonResponse(
        {
            "status": "ok",
            "entity_id": entity_id,
            "name": attributes.get("friendly_name") or entity_id,
            "value": display_value,
            "spoken_text": spoken_text,
        }
    )


class RFIDDataView(TemplateView):
    template_name = "nabhomeassistant/rfid-data.html"

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        uid = request.GET.get("uid", None)
        action = rfid_data.read_data_ui_for_views(uid)
        context["homeassistant_uid"] = uid
        context["action_type"] = action["action_type"]
        context["service_path"] = action["service_path"]
        context["entity_id"] = action["entity_id"]
        context["service_data"] = action["service_data"]
        context["speech_regex"] = action["speech_regex"]
        context["speech_replacement"] = action["speech_replacement"]
        return render(request, RFIDDataView.template_name, context=context)

    def post(self, request, *args, **kwargs):
        uid = request.POST.get("homeassistant_uid", "")
        service_data = request.POST.get("service_data", "").strip()

        if service_data:
            try:
                json.loads(service_data)
            except Exception:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Les donnees JSON ne sont pas valides.",
                    },
                    status=400,
                )

        action = {
            "action_type": request.POST.get("action_type", "read_state"),
            "service_path": request.POST.get("service_path", "").strip(),
            "entity_id": request.POST.get("entity_id", "").strip(),
            "service_data": service_data,
            "speech_regex": request.POST.get("speech_regex", "").strip(),
            "speech_replacement": request.POST.get(
                "speech_replacement", ""
            ).strip(),
        }
        rfid_data.write_data_ui_for_views(uid, action)
        return JsonResponse({"status": "ok", "data": "DATA_IN_LOCAL_DB"})
