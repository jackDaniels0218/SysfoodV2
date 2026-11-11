from django import forms

from .models import Inventario


class AjusteForm(forms.Form):
    nueva_cantidad = forms.DecimalField(label="Nueva cantidad disponible", min_value=0, max_digits=12, decimal_places=2,
                                        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}))
    motivo = forms.CharField(label="Motivo del ajuste", max_length=200, widget=forms.TextInput(attrs={"class": "form-control"}))

    def __init__(self, *args, inventario=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.inventario = inventario
        if inventario is not None:
            self.fields["nueva_cantidad"].widget.attrs["step"] = inventario.paso
            self.fields["nueva_cantidad"].label = f"Nueva cantidad disponible ({inventario.inv_unidad})"

    def clean_nueva_cantidad(self):
        cantidad = self.cleaned_data["nueva_cantidad"]
        if self.inventario is not None and cantidad is not None:
            self.inventario.validar_cantidad(cantidad)
        return cantidad


class BajaForm(forms.Form):
    motivo = forms.ChoiceField(label="Motivo de la baja", choices=Inventario.MOTIVOS_BAJA, widget=forms.Select(attrs={"class": "form-select"}))
    detalle = forms.CharField(label="Detalle", max_length=200, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))

    def clean(self):
        datos = super().clean()
        if datos.get("motivo") == "otro" and not (datos.get("detalle") or "").strip():
            self.add_error("detalle", "Describa el motivo de la baja.")
        return datos
