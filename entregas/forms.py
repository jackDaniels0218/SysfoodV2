from django import forms

from usuarios.forms import Fecha
from usuarios.models import Usuario

from .models import Entrega


class DatosEntregaForm(forms.ModelForm):
    class Meta:
        model = Entrega
        fields = ["ent_modalidad", "ent_dir_entrega", "ent_fec_prog", "responsable", "ent_obs"]
        widgets = {"ent_fec_prog": Fecha(), "ent_obs": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsable"].queryset = Usuario.objects.filter(usu_rol=Usuario.ADMIN, usu_estado=Usuario.ACTIVO)
        self.fields["ent_modalidad"].widget.attrs["data-modalidad"] = "dir-entrega"
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "form-select" if isinstance(campo.widget, forms.Select) else "form-control")

    def clean(self):
        datos = super().clean()
        if datos.get("ent_modalidad") == Entrega.DOMICILIO and not (datos.get("ent_dir_entrega") or "").strip():
            self.add_error("ent_dir_entrega", "Indique la dirección para la entrega a domicilio.")
        return datos
