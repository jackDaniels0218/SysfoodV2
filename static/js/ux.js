// Usabilidad: confirmaciones accesibles, búsqueda global (Ctrl+K o /), atajos de teclado,
// marcado de la página actual en el menú, guía de primeros pasos y esqueletos de carga.
(function () {
  "use strict";
  var bs = window.bootstrap;

  function escribiendo(e) {
    var t = e.target;
    return t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
  }
  function modalAbierto() { return !!document.querySelector(".modal.show"); }

  // ------------------------------------------------------------ Página actual en el menú (aria-current)
  var ruta = location.pathname;
  var mejor = null;
  document.querySelectorAll(".sf-nav a.nav-link[href], .sf-nav a.dropdown-item[href]").forEach(function (a) {
    var href = a.getAttribute("href");
    if (href && href !== "#" && href !== "/" && ruta.indexOf(href) === 0 && (!mejor || href.length > mejor.getAttribute("href").length)) { mejor = a; }
  });
  if (mejor) {
    mejor.setAttribute("aria-current", "page");
    mejor.classList.add("active");
    var menu = mejor.closest(".dropdown");
    if (menu) { menu.querySelector(".dropdown-toggle").classList.add("active"); }
  }

  // ------------------------------------------------------------ Confirmaciones con ventana propia
  var confirmar = document.getElementById("sf-confirmar");
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.matches || !form.matches("form[data-confirmar]") || form.dataset.confirmado === "1") { return; }
    e.preventDefault();
    e.stopImmediatePropagation();
    if (!confirmar || !bs) { if (window.confirm(form.dataset.confirmar)) { form.dataset.confirmado = "1"; form.requestSubmit ? form.requestSubmit(e.submitter) : form.submit(); } return; }
    document.getElementById("sf-confirmar-texto").textContent = form.dataset.confirmar;
    var si = document.getElementById("sf-confirmar-si");
    var modal = bs.Modal.getOrCreateInstance(confirmar);
    var aceptar = function () {
      si.removeEventListener("click", aceptar);
      form.dataset.confirmado = "1";
      modal.hide();
      if (form.requestSubmit) { form.requestSubmit(e.submitter || undefined); } else { form.submit(); }
    };
    si.addEventListener("click", aceptar);
    confirmar.addEventListener("hidden.bs.modal", function limpiar() {
      si.removeEventListener("click", aceptar);
      confirmar.removeEventListener("hidden.bs.modal", limpiar);
    });
    modal.show();
  }, true);
  if (confirmar) { confirmar.addEventListener("shown.bs.modal", function () { document.getElementById("sf-confirmar-si").focus(); }); }

  // ------------------------------------------------------------ Búsqueda global
  var paleta = document.getElementById("sf-paleta");
  var entrada = document.getElementById("sf-paleta-q");
  var lista = document.getElementById("sf-paleta-lista");
  var activo = -1, temporizador = null, ultima = "";

  function opciones() { return lista ? lista.querySelectorAll("[role=option]") : []; }
  function marcar(i) {
    var ops = opciones();
    if (!ops.length) { activo = -1; return; }
    activo = (i + ops.length) % ops.length;
    ops.forEach(function (o, j) { o.setAttribute("aria-selected", j === activo ? "true" : "false"); });
    entrada.setAttribute("aria-activedescendant", ops[activo].id);
    ops[activo].scrollIntoView({ block: "nearest" });
  }
  function esqueleto() {
    lista.innerHTML = "";
    for (var i = 0; i < 4; i++) {
      var s = document.createElement("div");
      s.className = "sf-esqueleto sf-esqueleto-fila";
      lista.appendChild(s);
    }
    lista.setAttribute("aria-busy", "true");
  }
  function mensaje(texto) {
    lista.innerHTML = "";
    var p = document.createElement("p");
    p.className = "sf-paleta-vacio"; p.textContent = texto;
    lista.appendChild(p);
  }
  function pintar(datos) {
    lista.innerHTML = ""; lista.removeAttribute("aria-busy");
    var n = 0;
    (datos.grupos || []).forEach(function (g) {
      var t = document.createElement("div");
      t.className = "sf-paleta-grupo"; t.textContent = g.nombre; t.setAttribute("role", "presentation");
      lista.appendChild(t);
      g.resultados.forEach(function (r) {
        var a = document.createElement("a");
        a.href = r.url; a.id = "sf-op-" + (n++); a.className = "sf-paleta-op";
        a.setAttribute("role", "option"); a.setAttribute("aria-selected", "false");
        var i = document.createElement("i"); i.className = "bi bi-" + (r.icono || "dot"); i.setAttribute("aria-hidden", "true");
        var s = document.createElement("span"); var b = document.createElement("strong"); b.textContent = r.titulo;
        var d = document.createElement("small"); d.textContent = r.detalle || "";
        s.appendChild(b); s.appendChild(d); a.appendChild(i); a.appendChild(s);
        lista.appendChild(a);
      });
    });
    entrada.setAttribute("aria-expanded", n ? "true" : "false");
    if (!n) { mensaje("Sin resultados para «" + datos.consulta + "». Pruebe con otra palabra, #número o código de entrega."); }
    activo = -1; if (n) { marcar(0); }
  }
  function consultar() {
    var q = entrada.value.trim();
    if (q === ultima) { return; }
    ultima = q;
    if (q.length < 2 && !/^#?\d+$/.test(q)) { mensaje("Escriba al menos dos letras."); entrada.setAttribute("aria-expanded", "false"); return; }
    esqueleto();
    fetch(paleta.dataset.url + "?formato=json&q=" + encodeURIComponent(q), { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (entrada.value.trim() === q) { pintar(d); } })
      .catch(function () { mensaje("No se pudo buscar. Revise su conexión."); });
  }
  function abrirBusqueda() {
    if (!paleta || !bs) { var enlace = document.getElementById("sf-buscar"); if (enlace) { location.href = enlace.href; } return; }
    bs.Modal.getOrCreateInstance(paleta).show();
  }
  if (paleta && bs) {
    paleta.addEventListener("shown.bs.modal", function () { entrada.focus(); entrada.select(); if (!entrada.value) { mensaje("Escriba para buscar páginas, personas, productos, #solicitud o un código de entrega."); } });
    entrada.addEventListener("input", function () { clearTimeout(temporizador); temporizador = setTimeout(consultar, 180); });
    entrada.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); marcar(activo + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); marcar(activo - 1); }
      else if (e.key === "Enter" && activo >= 0) { e.preventDefault(); opciones()[activo].click(); }
    });
    var boton = document.getElementById("sf-buscar");
    if (boton) { boton.addEventListener("click", function (e) { e.preventDefault(); abrirBusqueda(); }); }
  }

  // ------------------------------------------------------------ Atajos de teclado
  var rutas = {};
  try { rutas = JSON.parse((document.getElementById("sf-atajos-rutas") || {}).textContent || "{}"); } catch (err) { rutas = {}; }
  var esperandoG = false, tiempoG = null;
  document.addEventListener("keydown", function (e) {
    if (e.defaultPrevented) { return; }
    if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); abrirBusqueda(); return; }
    if (escribiendo(e) || e.altKey || e.ctrlKey || e.metaKey || modalAbierto()) { return; }
    if (esperandoG) {
      esperandoG = false; clearTimeout(tiempoG);
      if (rutas[e.key]) { e.preventDefault(); location.href = rutas[e.key]; }
      return;
    }
    if (e.key === "/" && paleta) { e.preventDefault(); abrirBusqueda(); }
    else if (e.key === "?") { e.preventDefault(); var m = document.getElementById("sf-atajos"); if (m && bs) { bs.Modal.getOrCreateInstance(m).show(); } }
    else if (e.key === "g" && Object.keys(rutas).length) { esperandoG = true; tiempoG = setTimeout(function () { esperandoG = false; }, 1200); }
    else if (e.key === "t") { var tema = document.getElementById("sf-tema"); if (tema) { tema.click(); } }
  });

  // ------------------------------------------------------------ Guía de primeros pasos (ocultar se recuerda en este navegador)
  var guia = document.querySelector("[data-guia]");
  if (guia) {
    var clave = "sf-guia-oculta";
    try { if (localStorage.getItem(clave) === "1") { guia.hidden = true; } } catch (err) { /* sin almacenamiento */ }
    var ocultar = guia.querySelector("[data-guia-ocultar]");
    if (ocultar) {
      ocultar.addEventListener("click", function () {
        guia.hidden = true;
        try { localStorage.setItem(clave, "1"); } catch (err) { /* sin almacenamiento */ }
      });
    }
  }

  // ------------------------------------------------------------ Esqueletos: se quitan cuando el contenido está listo
  document.querySelectorAll("canvas").forEach(function (c) {
    var caja = c.parentElement;
    if (!caja || caja.classList.contains("sf-esqueleto")) { return; }
    caja.classList.add("sf-esqueleto");
    var listo = function () { caja.classList.remove("sf-esqueleto"); };
    // Chart.js marca el lienzo al dibujar; como respaldo se quita al cargar la página.
    window.addEventListener("load", function () { setTimeout(listo, 150); });
  });
})();
