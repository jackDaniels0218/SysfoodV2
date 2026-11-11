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

  // La carga de documentos (cámara, arrastrar y soltar, progreso) está en js/carga.js.
});

/* ==========================================================================
   Experiencia visual: tema, progreso de lectura, animaciones de entrada,
   contadores, brillo que sigue al cursor y ondas en los botones.
   Todo respeta «reducir movimiento» del sistema.
   ========================================================================== */
(function () {
  "use strict";
  var sinMovimiento = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var raiz = document.documentElement;

  // --- Modo claro / oscuro ---
  var botonTema = document.getElementById("sf-tema");
  if (botonTema) {
    botonTema.addEventListener("click", function () {
      var nuevo = raiz.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
      raiz.setAttribute("data-bs-theme", nuevo);
      try { localStorage.setItem("sf-tema", nuevo); } catch (e) {}
      document.dispatchEvent(new CustomEvent("sf-tema", { detail: nuevo }));
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    // --- Barra de progreso de lectura ---
    var barra = document.getElementById("sf-progress");
    if (barra) {
      var pendiente = false;
      var actualizar = function () {
        var alto = document.documentElement.scrollHeight - window.innerHeight;
        barra.style.width = (alto > 0 ? Math.min(100, (window.scrollY / alto) * 100) : 0) + "%";
        pendiente = false;
      };
      window.addEventListener("scroll", function () { if (!pendiente) { pendiente = true; requestAnimationFrame(actualizar); } }, { passive: true });
      actualizar();
    }

    // --- Enlace activo en el menú ---
    var ruta = location.pathname;
    var mejor = null;
    document.querySelectorAll(".sf-nav a.nav-link[href], .sf-nav a.dropdown-item[href]").forEach(function (a) {
      var h = a.getAttribute("href");
      if (!h || h === "#" || h === "/") { return; }
      if (ruta === h || ruta.indexOf(h) === 0) {
        if (!mejor || h.length > mejor.getAttribute("href").length) { mejor = a; }
      }
    });
    if (mejor) {
      var objetivo = mejor.classList.contains("dropdown-item") ? mejor.closest(".dropdown").querySelector(".dropdown-toggle") : mejor;
      if (objetivo) { objetivo.classList.add("activo"); }
    }

    // --- Aparición escalonada al hacer scroll ---
    var candidatos = document.querySelectorAll("main .card, main .table-responsive, main .list-group, main .pasos, main .alert-info, main .ruta-item, main .marquee, main h1, main .tarjeta-indicador, main .producto-card");
    var elementos = [];
    candidatos.forEach(function (el) {
      if (el.closest(".reveal") && el.closest(".reveal") !== el) { return; }
      if (el.closest("[data-formset], template, .seccion-rol")) { return; }
      el.classList.add("reveal");
      elementos.push(el);
    });
    if (!("IntersectionObserver" in window) || sinMovimiento) {
      elementos.forEach(function (el) { el.classList.add("in"); });
    } else {
      var lote = 0, temporizador = null;
      var io = new IntersectionObserver(function (entradas) {
        entradas.forEach(function (e) {
          if (!e.isIntersecting) { return; }
          e.target.style.setProperty("--d", Math.min(lote * 0.07, 0.5) + "s");
          lote += 1;
          e.target.classList.add("in");
          io.unobserve(e.target);
          // Terminada la entrada, se libera el elemento para que el hover sea ágil.
          (function (el) { setTimeout(function () { el.classList.remove("reveal", "in"); el.style.removeProperty("--d"); }, 1400); })(e.target);
        });
        clearTimeout(temporizador);
        temporizador = setTimeout(function () { lote = 0; }, 120);
      }, { threshold: 0.08, rootMargin: "0px 0px -4% 0px" });
      elementos.forEach(function (el) { io.observe(el); });
    }

    // --- Contadores animados ---
    document.querySelectorAll(".numero").forEach(function (el) {
      var texto = el.textContent.trim();
      if (!/^\d+$/.test(texto)) { return; }
      var meta = parseInt(texto, 10);
      if (sinMovimiento || meta === 0) { return; }
      el.textContent = "0";
      var iniciado = false;
      var correr = function () {
        if (iniciado) { return; }
        iniciado = true;
        var t0 = performance.now(), dur = 900 + Math.min(meta, 500) * 1.2;
        (function paso(t) {
          var p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
          el.textContent = Math.round(meta * e);
          if (p < 1) { requestAnimationFrame(paso); } else { el.textContent = meta; }
        })(t0);
      };
      if ("IntersectionObserver" in window) {
        var o = new IntersectionObserver(function (es) { if (es[0].isIntersecting) { correr(); o.disconnect(); } }, { threshold: 0.4 });
        o.observe(el);
      } else { correr(); }
    });

    // --- Brillo que sigue al cursor en las tarjetas ---
    document.querySelectorAll(".tarjeta-indicador, .producto-card, .feature-card").forEach(function (c) {
      c.addEventListener("pointermove", function (e) {
        var r = c.getBoundingClientRect();
        c.style.setProperty("--mx", (e.clientX - r.left) + "px");
        c.style.setProperty("--my", (e.clientY - r.top) + "px");
      });
    });

    // --- Onda al pulsar botones ---
    document.addEventListener("click", function (e) {
      var b = e.target.closest(".btn-sysfood, .btn-warm, .btn-success, .btn-light");
      if (!b || sinMovimiento) { return; }
      var r = b.getBoundingClientRect(), d = Math.max(r.width, r.height);
      var s = document.createElement("span");
      s.className = "sf-ripple";
      s.style.cssText = "width:" + d + "px;height:" + d + "px;left:" + (e.clientX - r.left - d / 2) + "px;top:" + (e.clientY - r.top - d / 2) + "px";
      b.appendChild(s);
      setTimeout(function () { s.remove(); }, 650);
    });

    // --- Los avisos de éxito se retiran solos ---
    document.querySelectorAll(".alert-success.alert-dismissible, .alert-info.alert-dismissible").forEach(function (a) {
      setTimeout(function () {
        a.classList.add("sf-saliendo");
        setTimeout(function () { a.remove(); }, 520);
      }, 7000);
    });
  });
})();

// Botones que muestran «cargando» al enviar su formulario (evita envíos dobles).
document.addEventListener("submit", function (e) {
  var boton = e.submitter || e.target.querySelector("[data-cargando]");
  if (!boton || !boton.hasAttribute("data-cargando") || e.defaultPrevented) { return; }
  setTimeout(function () {
    boton.classList.add("sf-cargando");
    boton.setAttribute("aria-busy", "true");
    boton.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>' + boton.getAttribute("data-cargando");
  }, 0);
});

// Cantidades: las unidades contables (latas, cajas…) van en enteros y las divisibles (kg, L…) admiten decimales.
(function () {
  function ajustarPaso(select) {
    var divisibles = (select.getAttribute("data-divisibles") || "").split(",");
    var tarjeta = select.closest(".producto-form, form");
    var campo = tarjeta && tarjeta.querySelector("input[data-cantidad]");
    if (!campo || !select.value) { return; }
    var divisible = divisibles.indexOf(select.value) !== -1;
    var paso = divisible ? "0.01" : "1";
    campo.step = paso; campo.min = paso;
    campo.setCustomValidity("");
    if (!divisible && campo.value && Number(campo.value) % 1 !== 0) {
      campo.setCustomValidity("«" + select.value + "» se cuenta en unidades completas: escriba un número entero.");
    }
  }
  document.addEventListener("change", function (e) {
    if (e.target.matches && e.target.matches("select[data-divisibles]")) { ajustarPaso(e.target); }
  });
  document.addEventListener("input", function (e) {
    if (e.target.matches && e.target.matches("input[data-cantidad]")) {
      var tarjeta = e.target.closest(".producto-form, form");
      var select = tarjeta && tarjeta.querySelector("select[data-divisibles]");
      if (select) { ajustarPaso(select); }
    }
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("select[data-divisibles]").forEach(ajustarPaso);
  });
})();
