import datetime

from django.http import JsonResponse, QueryDict
from django.shortcuts import render
from django.views.generic import TemplateView

from .menu import MenuError, fetch_menu_json, meal_for_date
from .models import Config
from .nabmenudujour import NabMenuDuJour


class SettingsView(TemplateView):
    template_name = "nabmenudujour/settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["config"] = Config.load()
        return context

    def post(self, request, *args, **kwargs):
        config = Config.load()
        if "json_url" in request.POST:
            config.json_url = request.POST["json_url"]
        config.save()
        NabMenuDuJour.signal_daemon()
        context = self.get_context_data(**kwargs)
        return render(request, SettingsView.template_name, context=context)

    def put(self, request, *args, **kwargs):
        put_dict = QueryDict(request.body, encoding=request._encoding)
        if put_dict.get("type") == "preview":
            return self.preview(put_dict.get("json_url"))

        config = Config.load()
        if "json_url" in put_dict:
            config.json_url = put_dict["json_url"]
        config.next_performance_date = datetime.datetime.now(
            datetime.timezone.utc
        )
        config.next_performance_type = "today"
        config.save()
        NabMenuDuJour.signal_daemon()
        return JsonResponse({"status": "ok"})

    def preview(self, json_url=None):
        config = Config.load()
        if json_url is None:
            json_url = config.json_url
        try:
            data = fetch_menu_json(json_url)
            meal = meal_for_date(data)
            return JsonResponse({"status": "ok", "meal": meal})
        except MenuError as err:
            return JsonResponse({"status": "error", "message": str(err)})
        except Exception as err:
            return JsonResponse({"status": "error", "message": str(err)})


class RFIDDataView(TemplateView):
    template_name = "nabmenudujour/rfid-data.html"

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        return render(request, RFIDDataView.template_name, context=context)

    def post(self, request, *args, **kwargs):
        return JsonResponse({"data": ""})
