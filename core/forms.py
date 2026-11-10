from django import forms

from catalogo.models import Bodega

from . import parametros


class ParametroForm(forms.Form):
    par_valor = forms.CharField(label="Valor", max_length=500, required=False)

    def __init__(self, parametro, *args, **kwargs):
        self.parametro = parametro
        super().__init__(*args, **kwargs)
        definicion = parametros.definicion(parametro.par_clave)
        tipo = definicion.tipo
        campo = self.fields["par_valor"]
        campo.help_text = parametros.TIPOS_AYUDA.get(tipo, "")
        if tipo == "entero":
            attrs = {"class": "form-control", "min": 1 if definicion.minimo is None else definicion.minimo}
            if definicion.maximo is not None:
                attrs["max"] = definicion.maximo
            campo.widget = forms.NumberInput(attrs=attrs)
        elif tipo == "bodega":
            campo.widget = forms.Select(
                attrs={"class": "form-select"},
                choices=[("", "Primera bodega activa")] + [(str(b.pk), b.bod_nom) for b in Bodega.objects.filter(bod_estado="activa")],
            )
        elif tipo == "booleano":
            campo.widget = forms.Select(attrs={"class": "form-select"}, choices=[("si", "Sí"), ("no", "No")])
        elif tipo in ("grupos", "escala") or len(parametro.par_valor) > 60:
            campo.widget = forms.Textarea(attrs={"class": "form-control font-monospace", "rows": 3})
        else:
            campo.widget = forms.TextInput(attrs={"class": "form-control"})

    def clean_par_valor(self):
        valor = self.cleaned_data["par_valor"]
        if parametros.definicion(self.parametro.par_clave).tipo != "bodega" and not (valor or "").strip():
            raise forms.ValidationError("Este campo es obligatorio.")
        return parametros.validar(self.parametro.par_clave, valor)
