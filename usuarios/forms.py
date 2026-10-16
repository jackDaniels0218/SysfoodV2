from django import forms
from django.contrib.auth import password_validation
from django.utils import timezone

from .models import DocumentoValidacion, PerfilBeneficiario, PerfilDonante, Usuario


class BootstrapMixin:
    def _estilizar(self):
        for nombre, campo in self.fields.items():
            widget = campo.widget
            if isinstance(widget, (forms.CheckboxInput,)):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")


class Fecha(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class CuentaForm(BootstrapMixin, forms.ModelForm):
    """Datos de la cuenta comunes a todos los roles."""

    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text=password_validation.password_validators_help_text_html(), required=False)
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}), required=False)

    class Meta:
        model = Usuario
        fields = ["usu_correo", "usu_nom", "usu_ape", "usu_tel"]

    def __init__(self, *args, password_obligatoria=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.password_obligatoria = password_obligatoria
        self.fields["password1"].required = password_obligatoria
        self.fields["password2"].required = password_obligatoria
        self.fields["usu_tel"].widget.attrs["inputmode"] = "tel"
        self._estilizar()

    def clean_usu_correo(self):
        correo = self.cleaned_data["usu_correo"].strip().lower()
        existe = Usuario.objects.filter(usu_correo__iexact=correo)
        if self.instance.pk:
            existe = existe.exclude(pk=self.instance.pk)
        if existe.exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo.")
        return correo

    def clean_usu_tel(self):
        tel = self.cleaned_data["usu_tel"].strip()
        if not tel.replace("+", "").replace(" ", "").replace("-", "").isdigit():
            raise forms.ValidationError("Ingrese un teléfono válido (solo números).")
        return tel

    def clean(self):
        datos = super().clean()
        p1, p2 = datos.get("password1"), datos.get("password2")
        if p1 or p2 or self.password_obligatoria:
            if p1 != p2:
                self.add_error("password2", "Las contraseñas no coinciden.")
            elif p1:
                usuario = self.instance
                for campo in ("usu_correo", "usu_nom", "usu_ape"):
                    if datos.get(campo):
                        setattr(usuario, campo, datos[campo])
                try:
                    password_validation.validate_password(p1, usuario)
                except forms.ValidationError as error:
                    self.add_error("password1", error)
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=False)
        if self.cleaned_data.get("password1"):
            usuario.set_password(self.cleaned_data["password1"])
        if commit:
            usuario.save()
        return usuario


class RegistroForm(CuentaForm):
    usu_rol = forms.ChoiceField(
        label="Deseo registrarme como",
        choices=[(Usuario.DONANTE, "Donante"), (Usuario.BENEFICIARIO, "Beneficiario")],
        widget=forms.RadioSelect,
    )
    acepta = forms.BooleanField(
        label="Acepto la política de tratamiento de datos personales (Ley 1581 de 2012)", required=True,
        error_messages={"required": "Debe aceptar la política de tratamiento de datos para registrarse."},
    )

    field_order = ["usu_rol", "usu_nom", "usu_ape", "usu_correo", "usu_tel", "password1", "password2", "acepta"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["usu_rol"].widget.attrs = {"class": "form-check-input"}


class AdminUsuarioForm(CuentaForm):
    class Meta(CuentaForm.Meta):
        fields = ["usu_rol", "usu_correo", "usu_nom", "usu_ape", "usu_tel", "usu_estado"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["usu_rol"].disabled = True
            self.fields["usu_rol"].help_text = "El rol no se cambia después de crear la cuenta."
            self.fields["password1"].help_text = "Déjela vacía para conservar la contraseña actual."


class PerfilDonanteForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = PerfilDonante
        exclude = ["usuario"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._estilizar()

    def clean_don_doc_nit(self):
        valor = self.cleaned_data["don_doc_nit"].strip().upper()
        if not valor.replace("-", "").isalnum():
            raise forms.ValidationError("Ingrese un número de documento o NIT válido.")
        return valor


class PerfilBeneficiarioForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = PerfilBeneficiario
        exclude = ["usuario", "ben_estado_verif", "ben_fec_verif"]
        widgets = {"ben_fec_exp_doc": Fecha()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ben_fec_exp_doc"].widget.attrs["max"] = timezone.localdate().isoformat()
        self.fields["ben_num_personas"].widget.attrs["min"] = 1
        self._estilizar()

    def clean_ben_fec_exp_doc(self):
        fecha = self.cleaned_data["ben_fec_exp_doc"]
        if fecha and fecha > timezone.localdate():
            raise forms.ValidationError("La fecha de expedición no puede ser futura.")
        return fecha

    def clean_ben_num_doc(self):
        valor = self.cleaned_data["ben_num_doc"].strip().upper()
        if not valor.isalnum():
            raise forms.ValidationError("El número de documento solo admite letras y números.")
        return valor

    def clean_ben_num_personas(self):
        valor = self.cleaned_data["ben_num_personas"]
        if valor < 1 or valor > 30:
            raise forms.ValidationError("Ingrese un número de personas entre 1 y 30.")
        return valor


class PerfilUsuarioForm(CuentaForm):
    """Edición de los datos propios (sin rol ni estado)."""

    def __init__(self, *args, **kwargs):
        kwargs["password_obligatoria"] = False
        super().__init__(*args, **kwargs)
        self.fields["password1"].help_text = "Déjela vacía si no desea cambiarla."


class LoginForm(forms.Form):
    correo = forms.EmailField(label="Correo electrónico", widget=forms.EmailInput(attrs={"class": "form-control", "autofocus": True, "autocomplete": "email"}))
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "current-password"}))


class RecuperarForm(forms.Form):
    correo = forms.EmailField(label="Correo electrónico", widget=forms.EmailInput(attrs={"class": "form-control"}))


class NuevaPasswordForm(forms.Form):
    password1 = forms.CharField(label="Nueva contraseña", widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
                                help_text=password_validation.password_validators_help_text_html())
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}))

    def __init__(self, usuario, *args, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def clean(self):
        datos = super().clean()
        if datos.get("password1") and datos.get("password1") != datos.get("password2"):
            self.add_error("password2", "Las contraseñas no coinciden.")
        elif datos.get("password1"):
            try:
                password_validation.validate_password(datos["password1"], self.usuario)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return datos


class DocumentoForm(forms.Form):
    docv_tipo = forms.ChoiceField(label="Tipo de documento", widget=forms.Select(attrs={"class": "form-select"}))
    archivo = forms.FileField(label="Archivo", widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"}))
    docv_fec_venc = forms.DateField(label="Fecha de vencimiento (opcional)", required=False, widget=Fecha(attrs={"class": "form-control"}))

    def __init__(self, tipos, *args, **kwargs):
        super().__init__(*args, **kwargs)
        etiquetas = dict(DocumentoValidacion.TIPOS)
        self.fields["docv_tipo"].choices = [(t, etiquetas[t]) for t in tipos]


class RevisionDocumentoForm(forms.Form):
    decision = forms.ChoiceField(choices=[("aprobar", "Aprobar"), ("rechazar", "Rechazar")])
    observacion = forms.CharField(label="Observación", required=False, widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}))

    def clean(self):
        datos = super().clean()
        if datos.get("decision") == "rechazar" and not (datos.get("observacion") or "").strip():
            self.add_error("observacion", "Indique el motivo del rechazo.")
        return datos
