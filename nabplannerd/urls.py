from django.urls import path

from .views import PlannerView, RuleDeleteView, RuleRunView

urlpatterns = [
    path("", PlannerView.as_view(), name="nabplanner.index"),
    path("delete/<int:rule_id>", RuleDeleteView.as_view(), name="nabplanner.delete"),
    path("run/<int:rule_id>", RuleRunView.as_view(), name="nabplanner.run"),
]
