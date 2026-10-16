from django import forms

from catalogo.models import Bodega

from . import parametros


class ParametroForm(forms.Form):
    par_valor = forms.CharField(label="Valor", max_length=500)

    def __init__(self, parametro, *args, **kwargs):
        self.parametro = parametro
        super().__init__(*args, **kwargs)
        tipo = parametros.DEFINICIONES.get(parametro.par_clave, ("", "", "texto"))[2]
        campo = self.fields["par_valor"]
        if tipo == "entero":
            campo.widget = forms.NumberInput(attrs={"class": "form-control", "min": 1})
        elif tipo == "bodega":
            campo.required = False
            campo.widget = forms.Select(
                attrs={"class": "form-select"},
                choices=[("", "Primera bodega activa")] + [(str(b.pk), b.bod_nom) for b in Bodega.objects.filter(bod_estado="activa")],
            )
        else:
            campo.widget = forms.TextInput(attrs={"class": "form-control"})

    def clean_par_valor(self):
        try:
            return parametros.validar(self.parametro.par_clave, self.cleaned_data["par_valor"])
        except forms.ValidationError:
            raise
