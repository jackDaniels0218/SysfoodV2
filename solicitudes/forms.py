from django import forms
from django.utils import timezone

from catalogo.models import Bodega
from entregas.models import Entrega
from usuarios.forms import Fecha


class AprobarForm(forms.Form):
    modalidad = forms.ChoiceField(
        label="Modalidad",
        choices=Entrega.MODALIDADES,
        widget=forms.Select(attrs={"class": "form-select", "data-modalidad": "dir-aprobar"}),
    )
    direccion = forms.CharField(
        label="Dirección de entrega",
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    fecha_prog = forms.DateField(
        label="Fecha programada", required=False, widget=Fecha(attrs={"class": "form-control"})
    )
    bodega = forms.ModelChoiceField(
        label="Bodega de origen",
        queryset=Bodega.objects.filter(bod_estado="activa"),
        required=False,
        empty_label="La de los productos",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    observacion = forms.CharField(
        label="Observación", required=False, widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"})
    )

    def clean(self):
        datos = super().clean()
        if datos.get("modalidad") == Entrega.DOMICILIO and not (datos.get("direccion") or "").strip():
            self.add_error("direccion", "Indique la dirección para la entrega a domicilio.")
        if datos.get("fecha_prog") and datos["fecha_prog"] < timezone.localdate():
            self.add_error("fecha_prog", "La fecha programada no puede ser pasada.")
        return datos


class MotivoForm(forms.Form):
    observacion = forms.CharField(
        label="Motivo",
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        error_messages={"required": "El motivo es obligatorio."},
    )
