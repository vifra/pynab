import asyncio

from django.shortcuts import render
from django.views.generic import TemplateView

from nabweb.led_palette import choreography_color_palettes
from nabweb.views import NabWebView

from .models import Config


class SettingsView(TemplateView):
    template_name = "nabnetworkled/settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["config"] = Config.load()
        context["led_color_palettes"] = choreography_color_palettes()
        return context

    def post(self, request, *args, **kwargs):
        config = Config.load()
        if "ok_color" in request.POST:
            config.ok_color = self.normalize_color(request.POST["ok_color"])
            config.save()
            asyncio.run(NabWebView().notify_config_update("nabd", "network_led"))
        context = self.get_context_data(**kwargs)
        return render(request, SettingsView.template_name, context=context)

    def normalize_color(self, color):
        color = (color or "").strip()
        if not color.startswith("#"):
            color = f"#{color}"
        if len(color) != 7:
            return "#ff00ff"
        try:
            int(color[1:], 16)
        except ValueError:
            return "#ff00ff"
        return color.lower()
