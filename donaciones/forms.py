from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from catalogo.models import Categoria
from core import parametros
from inventario import unidades as uds
from usuarios.forms import BootstrapMixin, Fecha

from .models import DetalleDonacion, Donacion


class DonacionForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Donacion
        fields = ["dona_anonima", "dona_obs"]
        widgets = {"dona_obs": forms.Textarea(attrs={"rows": 2})}
        labels = {"dona_anonima": "Registrar esta donación de forma anónima"}
        help_texts = {"dona_anonima": "Los beneficiarios y las consultas públicas verán «Donante anónimo». "
                                      "Solo el administrador puede conocer su identidad."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._estilizar()


class DetalleForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = DetalleDonacion
        fields = ["categoria", "dd_nom", "dd_desc", "dd_cantidad", "dd_unidad", "dd_fec_venc", "dd_lote"]
        widgets = {"dd_fec_venc": Fecha()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categorias = Categoria.objects.filter(cat_estado="activa")
        if self.instance.pk:
            categorias = Categoria.objects.filter(pk=self.instance.categoria_id) | categorias
        self.fields["categoria"].queryset = categorias.distinct()
        unidades = parametros.lista("unidades_medida")
        if self.instance.pk and self.instance.dd_unidad not in unidades:
            unidades.append(self.instance.dd_unidad)
        self.fields["dd_unidad"] = forms.ChoiceField(label="Unidad", choices=[("", "---------")] + [(u, u.capitalize()) for u in unidades])
        divisibles = [u for u in unidades if uds.es_divisible(u)]
        # El JS (sysfood.js) cambia el paso del campo cantidad al elegir la unidad: 1 en contables, 0,01 en divisibles.
        self.fields["dd_unidad"].widget.attrs["data-divisibles"] = ",".join(divisibles)
        actual = self.instance.dd_unidad if self.instance.pk else ""
        paso = uds.paso(actual) if actual else "0.01"
        self.fields["dd_cantidad"].widget.attrs.update({"min": paso, "step": paso, "data-cantidad": "1"})
        self.fields["dd_cantidad"].help_text = "Kilos, litros y demás medidas admiten decimales; latas, cajas y unidades van en enteros."
        self.fields["dd_fec_venc"].widget.attrs["min"] = (timezone.localdate() + timezone.timedelta(days=1)).isoformat()
        self._estilizar()

    def clean_dd_fec_venc(self):
        fecha = self.cleaned_data["dd_fec_venc"]
        if fecha <= timezone.localdate():
            raise forms.ValidationError("La fecha de vencimiento debe ser posterior a hoy.")
        return fecha

    def clean_dd_cantidad(self):
        cantidad = self.cleaned_data["dd_cantidad"]
        if cantidad is None or cantidad <= 0:
            raise forms.ValidationError("La cantidad debe ser mayor que cero.")
        return cantidad


class DetalleFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        vigentes = [f for f in self.forms if f.cleaned_data and not f.cleaned_data.get("DELETE")]
        if not vigentes:
            raise forms.ValidationError("Agregue al menos un producto a la donación.")


DetalleFormSetCrear = inlineformset_factory(
    Donacion, DetalleDonacion, form=DetalleForm, formset=DetalleFormSet, extra=1, can_delete=False,
)
DetalleFormSetEditar = inlineformset_factory(
    Donacion, DetalleDonacion, form=DetalleForm, formset=DetalleFormSet, extra=0, can_delete=True,
)


class CancelarForm(forms.Form):
    motivo = forms.CharField(label="Motivo", max_length=200, widget=forms.TextInput(attrs={"class": "form-control"}))
