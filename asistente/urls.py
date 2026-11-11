from django.urls import path

from . import views

app_name = "asistente"

urlpatterns = [
    path("inicio/", views.inicio, name="inicio"),
    path("preguntar/", views.preguntar, name="preguntar"),
    path("consulta/<int:pk>/calificar/", views.calificar, name="calificar"),
    path("consulta/<int:pk>/contactar/", views.contactar, name="contactar"),
    path("consultas/", views.panel, name="panel"),
    path("consultas/<int:pk>/atender/", views.atender, name="atender"),
    path("whatsapp/", views.whatsapp_webhook, name="whatsapp"),
]
