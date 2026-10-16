from django import forms

from usuarios.forms import BootstrapMixin
from usuarios.models import Usuario

from .models import Bodega, Categoria


class CategoriaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["cat_nom", "cat_desc", "cat_perecedero", "cat_dias_alerta", "cat_estado"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cat_dias_alerta"].widget.attrs.update({"min": 1, "max": 365})
        self._estilizar()

    def clean_cat_nom(self):
        nombre = self.cleaned_data["cat_nom"].strip()
        existe = Categoria.objects.filter(cat_nom__iexact=nombre).exclude(pk=self.instance.pk)
        if existe.exists():
            raise forms.ValidationError("Ya existe una categoría con ese nombre.")
        return nombre

    def clean_cat_dias_alerta(self):
        dias = self.cleaned_data.get("cat_dias_alerta")
        if dias is not None and not 1 <= dias <= 365:
            raise forms.ValidationError("Ingrese un valor entre 1 y 365 días.")
        return dias


class BodegaForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Bodega
        fields = ["bod_nom", "bod_dir", "bod_capacidad", "responsable", "bod_estado"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsable"].queryset = Usuario.objects.filter(usu_rol=Usuario.ADMIN, usu_estado=Usuario.ACTIVO)
        self.fields["responsable"].label_from_instance = lambda u: f"{u.nombre_completo} ({u.usu_correo})"
        self._estilizar()

    def clean_bod_nom(self):
        nombre = self.cleaned_data["bod_nom"].strip()
        if Bodega.objects.filter(bod_nom__iexact=nombre).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una bodega con ese nombre.")
        return nombre
