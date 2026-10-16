"""Carga datos de demostración para probar SysFood V2 de inmediato."""
from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalogo.models import Bodega, Categoria
from core.models import Parametro
from donaciones import servicios as don_srv
from donaciones.models import DetalleDonacion, Donacion
from solicitudes import servicios as sol_srv
from usuarios import servicios as usu_srv
from usuarios.models import DocumentoValidacion, PerfilBeneficiario, PerfilDonante, Usuario

CLAVE = "Sysfood2025*"

PDF_MINIMO = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 60>>stream\nBT /F1 14 Tf 20 70 Td (Documento de prueba SysFood) Tj ET\nendstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
)


def _pdf(nombre, marca):
    return SimpleUploadedFile(nombre, PDF_MINIMO + f"% {marca}\n".encode(), content_type="application/pdf")


class Command(BaseCommand):
    help = "Crea usuarios, categorías, bodegas, donaciones y solicitudes de demostración."

    def add_arguments(self, parser):
        parser.add_argument("--solo-admin", action="store_true", help="Crea solo el administrador inicial.")

    @transaction.atomic
    def handle(self, *args, **opciones):
        hoy = timezone.localdate()
        admin, creado = Usuario.objects.get_or_create(
            usu_correo="admin@sysfood.local",
            defaults=dict(usu_rol=Usuario.ADMIN, usu_nom="Ana", usu_ape="Administradora", usu_tel="3001112233",
                          usu_acepta_datos=True, usu_fec_acepta=timezone.now()),
        )
        if creado:
            admin.set_password(CLAVE)
            admin.save()
        if opciones["solo_admin"]:
            self.stdout.write(self.style.SUCCESS(f"Administrador: admin@sysfood.local / {CLAVE}"))
            return
        if Donacion.objects.exists():
            self.stdout.write(self.style.WARNING("Ya existen donaciones; no se cargan datos de demostración otra vez."))
            return

        bodega, _ = Bodega.objects.get_or_create(
            bod_nom="Bodega Central Facatativá",
            defaults=dict(responsable=admin, bod_dir="Calle 14 # 15-20, Facatativá", bod_capacidad="2.000 kg"),
        )
        Bodega.objects.get_or_create(bod_nom="Bodega Norte", defaults=dict(responsable=admin, bod_dir="Carrera 2 # 8-40", bod_capacidad="800 kg"))
        Parametro.objects.filter(par_clave="bodega_predeterminada").update(par_valor=str(bodega.pk), usuario_mod=admin)

        categorias = {}
        for nombre, desc, perecedero, dias in [
            ("Granos", "Arroz, fríjol, lenteja, garbanzo", False, None),
            ("Lácteos", "Leche, queso, yogur", True, 5),
            ("Enlatados", "Atún, sardinas, verduras en lata", False, 30),
            ("Frutas y verduras", "Productos frescos", True, 3),
            ("Aseo", "Jabón, detergente, papel higiénico", False, None),
        ]:
            categorias[nombre], _ = Categoria.objects.get_or_create(
                cat_nom=nombre, defaults=dict(cat_desc=desc, cat_perecedero=perecedero, cat_dias_alerta=dias),
            )

        def usuario(correo, rol, nom, ape, tel):
            u = Usuario(usu_correo=correo, usu_rol=rol, usu_nom=nom, usu_ape=ape, usu_tel=tel,
                        usu_acepta_datos=True, usu_fec_acepta=timezone.now())
            u.set_password(CLAVE)
            u.save()
            return u

        d1 = usuario("donante@sysfood.local", Usuario.DONANTE, "Carlos", "Pérez", "3105556677")
        PerfilDonante.objects.create(usuario=d1, don_tipo_persona="natural", don_tipo_doc="CC", don_doc_nit="1070123456",
                                     don_dir="Cra 5 # 10-12, Facatativá", don_frecuencia="mensual")
        d2 = usuario("empresa@sysfood.local", Usuario.DONANTE, "Laura", "Gómez", "3209998877")
        PerfilDonante.objects.create(usuario=d2, don_tipo_persona="juridica", don_tipo_doc="NIT", don_doc_nit="900123456-7",
                                     don_raz_soc="Alimentos La Sabana S.A.S.", don_contacto="Laura Gómez",
                                     don_dir="Zona Industrial km 2", don_anonimo_def=True)

        b1 = usuario("beneficiario@sysfood.local", Usuario.BENEFICIARIO, "María", "Rodríguez", "3014445566")
        PerfilBeneficiario.objects.create(usuario=b1, ben_tipo_doc="CC", ben_num_doc="52123456", ben_fec_exp_doc=date(2010, 5, 20),
                                          ben_dir="Barrio Santa Rita, Cl 3 # 4-10", ben_num_personas=4, ben_sisben="A", ben_estrato=1)
        for tipo in (DocumentoValidacion.IDENTIDAD, DocumentoValidacion.SISBEN, DocumentoValidacion.RESIDENCIA):
            doc = usu_srv.cargar_documento(b1, tipo, _pdf(f"{tipo}.pdf", f"b1-{tipo}"))
            usu_srv.revisar_documento(doc, admin, True)

        b2 = usuario("nuevo@sysfood.local", Usuario.BENEFICIARIO, "Jorge", "Martínez", "3127778899")
        PerfilBeneficiario.objects.create(usuario=b2, ben_tipo_doc="CC", ben_num_doc="80987654", ben_fec_exp_doc=date(2005, 3, 2),
                                          ben_dir="Vereda El Corzo", ben_num_personas=6, ben_sisben="B", ben_estrato=2, ben_discapacidad=True)
        for tipo in (DocumentoValidacion.IDENTIDAD, DocumentoValidacion.SISBEN, DocumentoValidacion.RESIDENCIA, DocumentoValidacion.DISCAPACIDAD):
            usu_srv.cargar_documento(b2, tipo, _pdf(f"{tipo}.pdf", f"b2-{tipo}"))

        def donar(donante, anonima, productos, obs=""):
            don = Donacion(donante=donante, dona_anonima=anonima, dona_obs=obs)
            detalles = [
                DetalleDonacion(categoria=categorias[c], dd_nom=n, dd_cantidad=Decimal(q), dd_unidad=u, dd_fec_venc=hoy + timedelta(days=dias), dd_lote=lote)
                for c, n, q, u, dias, lote in productos
            ]
            return don_srv.registrar(don, detalles, donante)

        donar(d1, False, [
            ("Granos", "Arroz blanco", "50", "kilogramos", 240, "AR-2201"),
            ("Granos", "Fríjol rojo", "20", "kilogramos", 200, ""),
            ("Lácteos", "Leche entera UHT", "24", "litros", 4, "LE-778"),
        ], "Entrega en la bodega central")
        donar(d2, True, [
            ("Enlatados", "Atún en aceite", "60", "latas", 400, "AT-10"),
            ("Aseo", "Jabón de baño", "40", "unidades", 700, ""),
            ("Frutas y verduras", "Papa pastusa", "30", "kilogramos", 12, ""),
        ], "Donación corporativa trimestral")

        from inventario.models import Inventario
        arroz = Inventario.objects.get(inv_nom="Arroz blanco")
        atun = Inventario.objects.get(inv_nom="Atún en aceite")
        sol_srv.agregar_al_carrito(b1, arroz, "5")
        sol_srv.agregar_al_carrito(b1, atun, "6")
        sol_srv.enviar_solicitud(b1)

        from core.tareas import ejecutar_control_diario
        ejecutar_control_diario(forzar=True)

        self.stdout.write(self.style.SUCCESS("Datos de demostración cargados. Contraseña de todas las cuentas: " + CLAVE))
        for correo, rol in [
            ("admin@sysfood.local", "Administrador"),
            ("donante@sysfood.local", "Donante (persona natural)"),
            ("empresa@sysfood.local", "Donante (persona jurídica, anónimo por defecto)"),
            ("beneficiario@sysfood.local", "Beneficiario verificado (con una solicitud pendiente)"),
            ("nuevo@sysfood.local", "Beneficiario con documentos en revisión"),
        ]:
            self.stdout.write(f"  {correo:30} {rol}")
