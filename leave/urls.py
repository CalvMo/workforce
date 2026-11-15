from django.urls import path

from . import views

app_name = "leave"

urlpatterns = [
    path("", views.my_leave, name="mine"),
    path("<int:pk>/cancel/", views.cancel, name="cancel"),
    path("approvals/", views.approvals, name="approvals"),
    path("approvals/<int:pk>/", views.decide, name="decide"),
    path("team/", views.team_calendar, name="team"),
]
