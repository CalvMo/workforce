from django.urls import path

from . import views

app_name = "timesheets"

urlpatterns = [
    path("", views.week, name="week"),
    path("history/", views.history, name="history"),
    path("approvals/", views.approvals, name="approvals"),
    path("<int:pk>/", views.review, name="review"),
    path("<int:pk>/decide/", views.decide, name="decide"),
]
