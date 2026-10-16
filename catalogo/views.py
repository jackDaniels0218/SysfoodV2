from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.permisos import solo_admin
from core.servicios import auditar

from .forms import BodegaForm, CategoriaForm
from .models import Bodega, Categoria


@solo_admin
def categorias(request):
    lista = Categoria.objects.annotate(productos=Count("inventario")).order_by("cat_nom")
    q = request.GET.get("q", "").strip()
    if q:
        lista = lista.filter(Q(cat_nom__icontains=q) | Q(cat_desc__icontains=q))
    if request.GET.get("estado"):
        lista = lista.filter(cat_estado=request.GET["estado"])
    return render(request, "catalogo/categorias.html", {"lista": lista})


def _guardar(request, form, entidad, objeto=None):
    nuevo = form.instance.pk is None
    instancia = form.save()
    auditar(request, "crear" if nuevo else "editar", entidad, instancia.pk, str(instancia))
    return instancia


@solo_admin
def categoria_form(request, pk=None):
    objeto = get_object_or_404(Categoria, pk=pk) if pk else None
    form = CategoriaForm(request.POST or None, instance=objeto)
    if request.method == "POST" and form.is_valid():
        _guardar(request, form, "categoria")
        messages.success(request, "Categoría guardada.")
        return redirect("catalogo:categorias")
    return render(request, "catalogo/form.html", {"form": form, "titulo": "Editar categoría" if objeto else "Nueva categoría", "volver": "catalogo:categorias"})


@solo_admin
@require_POST
def categoria_eliminar(request, pk):
    objeto = get_object_or_404(Categoria, pk=pk)
    if objeto.detalles_donacion.exists() or objeto.inventario.exists():
        objeto.cat_estado = "inactiva"
        objeto.save()
        auditar(request, "cambio_estado", "categoria", pk, "Inactivada: tiene productos asociados")
        messages.warning(request, "La categoría tiene productos asociados, por eso se inactivó en lugar de eliminarse.")
    else:
        nombre = str(objeto)
        objeto.delete()
        auditar(request, "eliminar", "categoria", pk, nombre)
        messages.success(request, "Categoría eliminada.")
    return redirect("catalogo:categorias")


@solo_admin
def bodegas(request):
    lista = Bodega.objects.select_related("responsable").annotate(
        productos=Count("inventario", filter=~Q(inventario__inv_estado="retirado")),
        existencias=Sum("inventario__inv_cant_disp", filter=~Q(inventario__inv_estado="retirado")),
    ).order_by("bod_nom")
    return render(request, "catalogo/bodegas.html", {"lista": lista})


@solo_admin
def bodega_form(request, pk=None):
    objeto = get_object_or_404(Bodega, pk=pk) if pk else None
    form = BodegaForm(request.POST or None, instance=objeto)
    if request.method == "POST" and form.is_valid():
        _guardar(request, form, "bodega")
        messages.success(request, "Bodega guardada.")
        return redirect("catalogo:bodegas")
    return render(request, "catalogo/form.html", {"form": form, "titulo": "Editar bodega" if objeto else "Nueva bodega", "volver": "catalogo:bodegas"})


@solo_admin
@require_POST
def bodega_eliminar(request, pk):
    objeto = get_object_or_404(Bodega, pk=pk)
    if objeto.inventario.exists() or objeto.entregas.exists():
        objeto.bod_estado = "inactiva"
        objeto.save()
        auditar(request, "cambio_estado", "bodega", pk, "Inactivada: tiene inventario asociado")
        messages.warning(request, "La bodega tiene inventario asociado, por eso se inactivó en lugar de eliminarse.")
    else:
        nombre = str(objeto)
        objeto.delete()
        auditar(request, "eliminar", "bodega", pk, nombre)
        messages.success(request, "Bodega eliminada.")
    return redirect("catalogo:bodegas")
