// Comportamientos comunes de la interfaz.
document.addEventListener("DOMContentLoaded", function () {
  // Formularios con secciones por rol (registro y administración de usuarios).
  function actualizarSecciones() {
    var elegido = document.querySelector("[name='usu_rol']:checked") || document.querySelector("select[name='usu_rol']");
    var rol = elegido ? elegido.value : "";
    document.querySelectorAll(".seccion-rol").forEach(function (s) {
      var visible = s.dataset.rol === rol;
      s.classList.toggle("visible", visible);
      s.querySelectorAll("input, select, textarea").forEach(function (c) { c.disabled = !visible; });
    });
  }
  document.querySelectorAll("[name='usu_rol']").forEach(function (c) { c.addEventListener("change", actualizarSecciones); });
  if (document.querySelector(".seccion-rol")) { actualizarSecciones(); }

  // Donante: la razón social solo aplica a persona jurídica.
  var tipoPersona = document.querySelector("[name='don-don_tipo_persona']");
  function razonSocial() {
    var juridica = tipoPersona && tipoPersona.value === "juridica";
    document.querySelectorAll(".solo-juridica").forEach(function (e) { e.classList.toggle("d-none", !juridica); });
    var tipoDoc = document.querySelector("[name='don-don_tipo_doc']");
    if (juridica && tipoDoc) { tipoDoc.value = "NIT"; }
  }
  if (tipoPersona) { tipoPersona.addEventListener("change", razonSocial); razonSocial(); }

  // Entrega: la dirección solo aplica a domicilio.
  document.querySelectorAll("[data-modalidad]").forEach(function (sel) {
    var objetivo = document.getElementById(sel.dataset.modalidad);
    function cambiar() { if (objetivo) { objetivo.classList.toggle("d-none", sel.value !== "domicilio"); } }
    sel.addEventListener("change", cambiar); cambiar();
  });

  // Confirmaciones.
  document.querySelectorAll("form[data-confirmar]").forEach(function (f) {
    f.addEventListener("submit", function (e) { if (!confirm(f.dataset.confirmar)) { e.preventDefault(); } });
  });

  // Formsets dinámicos (productos de la donación).
  document.querySelectorAll("[data-formset]").forEach(function (contenedor) {
    var prefijo = contenedor.dataset.formset;
    var total = document.getElementById("id_" + prefijo + "-TOTAL_FORMS");
    var plantilla = document.getElementById("plantilla-" + prefijo);
    var boton = document.querySelector("[data-agregar='" + prefijo + "']");
    if (!boton || !plantilla || !total) { return; }
    boton.addEventListener("click", function () {
      var indice = parseInt(total.value, 10);
      var html = plantilla.innerHTML.replace(/__prefix__/g, indice);
      contenedor.insertAdjacentHTML("beforeend", html);
      total.value = indice + 1;
    });
    contenedor.addEventListener("click", function (e) {
      var quitar = e.target.closest("[data-quitar]");
      if (!quitar) { return; }
      var tarjeta = quitar.closest(".producto-form");
      var borrar = tarjeta.querySelector("input[name$='-DELETE']");
      if (borrar) { borrar.checked = true; tarjeta.classList.add("d-none"); }
      else { tarjeta.querySelectorAll("input, select, textarea").forEach(function (c) { c.value = ""; }); tarjeta.classList.add("d-none"); }
    });
  });

  // Captura con cámara: copia el archivo tomado al campo principal.
  var camara = document.getElementById("archivo-camara");
  var principal = document.getElementById("id_archivo");
  if (camara && principal) {
    camara.addEventListener("change", function () {
      if (camara.files.length) {
        var dt = new DataTransfer();
        dt.items.add(camara.files[0]);
        principal.files = dt.files;
        var aviso = document.getElementById("aviso-camara");
        if (aviso) { aviso.textContent = "Foto lista: " + camara.files[0].name; }
      }
    });
  }
});
