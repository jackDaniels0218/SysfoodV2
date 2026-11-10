/* Carga de documentos: arrastrar y soltar, cámara, vista previa, reducción de fotos grandes,
   validación previa y barra de progreso. Sin JavaScript, el formulario funciona igual (envío normal). */
(function () {
  "use strict";
  var form = document.getElementById("form-carga");
  if (!form || !window.FormData || !window.XMLHttpRequest) { return; }

  var zona = document.getElementById("zona-carga");
  var principal = document.getElementById("id_archivo");
  var camara = document.getElementById("archivo-camara");
  var previa = document.getElementById("previa");
  var progreso = document.getElementById("progreso");
  var barra = progreso.querySelector(".progress-bar");
  var mensaje = document.getElementById("mensaje-carga");
  var boton = document.getElementById("boton-carga");
  var formatos = (form.dataset.formatos || "pdf,jpg,png").split(",");
  var maxBytes = parseFloat(form.dataset.maxMb || "5") * 1024 * 1024;
  var LADO_MAX = 2200;
  var elegido = null;

  function avisar(texto, tipo) {
    mensaje.className = "small mb-2 " + (tipo === "error" ? "text-danger" : tipo === "ok" ? "text-success" : tipo === "aviso" ? "text-warning-emphasis" : "text-muted");
    mensaje.innerHTML = texto ? '<i class="bi ' + (tipo === "error" ? "bi-exclamation-circle" : tipo === "ok" ? "bi-check-circle" : "bi-info-circle") + '" aria-hidden="true"></i> ' : "";
    mensaje.appendChild(document.createTextNode(texto || ""));
  }

  function extension(nombre) {
    var e = (nombre.split(".").pop() || "").toLowerCase();
    return e === "jpeg" ? "jpg" : e;
  }

  function tamano(bytes) {
    return bytes > 1048576 ? (bytes / 1048576).toFixed(1).replace(".", ",") + " MB" : Math.round(bytes / 1024) + " KB";
  }

  function mostrarPrevia(archivo) {
    previa.innerHTML = "";
    var figura;
    if (archivo.type.indexOf("image/") === 0) {
      figura = document.createElement("img");
      figura.alt = "Vista previa del documento";
      figura.src = URL.createObjectURL(archivo);
    } else {
      figura = document.createElement("div");
      figura.className = "sf-previa-pdf";
      figura.innerHTML = '<i class="bi bi-file-earmark-pdf" aria-hidden="true"></i>';
    }
    var datos = document.createElement("div");
    datos.className = "small flex-grow-1 text-break";
    datos.innerHTML = "<strong></strong><div class='text-muted'></div>";
    datos.querySelector("strong").textContent = archivo.name;
    datos.querySelector("div").textContent = tamano(archivo.size) + " · listo para cargar";
    var quitar = document.createElement("button");
    quitar.type = "button";
    quitar.className = "btn btn-sm btn-outline-secondary";
    quitar.setAttribute("aria-label", "Quitar archivo");
    quitar.innerHTML = '<i class="bi bi-x-lg" aria-hidden="true"></i>';
    quitar.addEventListener("click", function () { elegido = null; previa.hidden = true; principal.value = ""; camara.value = ""; avisar(""); });
    previa.appendChild(figura); previa.appendChild(datos); previa.appendChild(quitar);
    previa.hidden = false;
  }

  /* Reduce fotos grandes (las del celular suelen pasar de 5 MB) a JPEG de máximo 2200 px. */
  function reducir(archivo) {
    return new Promise(function (resolver) {
      if (archivo.type.indexOf("image/") !== 0 || formatos.indexOf("jpg") < 0 || !window.createImageBitmap) { return resolver(archivo); }
      createImageBitmap(archivo).then(function (img) {
        var escala = Math.min(1, LADO_MAX / Math.max(img.width, img.height));
        if (escala === 1 && archivo.size <= maxBytes) { return resolver(archivo); }
        var lienzo = document.createElement("canvas");
        lienzo.width = Math.round(img.width * escala);
        lienzo.height = Math.round(img.height * escala);
        lienzo.getContext("2d").drawImage(img, 0, 0, lienzo.width, lienzo.height);
        lienzo.toBlob(function (blob) {
          if (!blob) { return resolver(archivo); }
          var nombre = archivo.name.replace(/\.[^.]+$/, "") + ".jpg";
          resolver(new File([blob], nombre, { type: "image/jpeg" }));
        }, "image/jpeg", 0.86);
      }).catch(function () { resolver(archivo); });
    });
  }

  function elegir(archivo) {
    if (!archivo) { return; }
    var ext = extension(archivo.name || "");
    if (formatos.indexOf(ext) < 0 && !(archivo.type.indexOf("image/") === 0 && formatos.indexOf("jpg") >= 0)) {
      elegido = null; previa.hidden = true;
      return avisar("Formato no permitido. Use: " + formatos.join(", ").toUpperCase() + ".", "error");
    }
    avisar("Preparando el archivo…");
    reducir(archivo).then(function (listo) {
      if (listo.size > maxBytes) {
        elegido = null; previa.hidden = true;
        return avisar("El archivo pesa " + tamano(listo.size) + " y supera el máximo de " + form.dataset.maxMb + " MB.", "error");
      }
      elegido = listo;
      mostrarPrevia(listo);
      avisar(listo !== archivo ? "Foto reducida a " + tamano(listo.size) + " para cargarla más rápido." : "");
    });
  }

  principal.addEventListener("change", function () { elegir(principal.files[0]); });
  camara.addEventListener("change", function () {
    elegir(camara.files[0]);
    var aviso = document.getElementById("aviso-camara");
    if (aviso && camara.files[0]) { aviso.textContent = "Foto tomada."; }
  });
  ["dragenter", "dragover"].forEach(function (ev) {
    zona.addEventListener(ev, function (e) { e.preventDefault(); zona.classList.add("sobre"); });
  });
  ["dragleave", "drop"].forEach(function (ev) {
    zona.addEventListener(ev, function (e) { e.preventDefault(); zona.classList.remove("sobre"); });
  });
  zona.addEventListener("drop", function (e) {
    if (e.dataTransfer && e.dataTransfer.files.length) { elegir(e.dataTransfer.files[0]); }
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!elegido) { avisar("Elija un archivo o tome una foto antes de cargar.", "error"); return; }
    var datos = new FormData(form);
    datos.delete("archivo");
    datos.append("archivo", elegido, elegido.name);
    var xhr = new XMLHttpRequest();
    xhr.open("POST", form.action || location.href);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    progreso.hidden = false;
    barra.style.width = "0%";
    boton.disabled = true;
    boton.setAttribute("aria-busy", "true");
    avisar("Cargando…");
    xhr.upload.onprogress = function (ev) {
      if (!ev.lengthComputable) { return; }
      var p = Math.round(ev.loaded / ev.total * 100);
      barra.style.width = p + "%";
      progreso.setAttribute("aria-valuenow", p);
      if (p >= 100) { avisar("Archivo recibido. El sistema lo está leyendo y verificando…"); }
    };
    xhr.onload = function () {
      var r = {};
      try { r = JSON.parse(xhr.responseText); } catch (err) { r = { ok: false, mensaje: "Respuesta inesperada del servidor." }; }
      boton.disabled = false;
      boton.removeAttribute("aria-busy");
      if (r.ok) {
        barra.style.width = "100%";
        avisar(r.mensaje, r.nivel === "warning" ? "aviso" : "ok");
        setTimeout(function () { location.href = r.destino || location.pathname; }, r.nivel === "warning" ? 3500 : 1600);
      } else {
        progreso.hidden = true;
        avisar(r.mensaje || "No se pudo cargar el archivo.", "error");
      }
    };
    xhr.onerror = function () {
      boton.disabled = false; progreso.hidden = true;
      avisar("Se perdió la conexión. Revise su internet e intente de nuevo; el archivo sigue seleccionado.", "error");
    };
    xhr.send(datos);
  });
})();
