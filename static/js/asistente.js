// Asistente de ayuda: widget flotante disponible en todas las páginas.
(function () {
  var raiz = document.getElementById("sf-chat");
  if (!raiz) { return; }
  var boton = document.getElementById("sf-chat-boton");
  var panel = document.getElementById("sf-chat-panel");
  var lista = document.getElementById("sf-chat-mensajes");
  var chips = document.getElementById("sf-chat-sugerencias");
  var form = document.getElementById("sf-chat-form");
  var entrada = document.getElementById("sf-chat-texto");
  var anonimo = raiz.dataset.anonimo === "1";
  var base = raiz.dataset.base.replace(/inicio\/$/, "");
  var iniciado = false;
  var ocupado = false;

  function cookie(nombre) {
    var m = document.cookie.match("(^|;)\\s*" + nombre + "=([^;]+)");
    return m ? decodeURIComponent(m[2]) : "";
  }

  function enviarJSON(url, datos) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": cookie("csrftoken"), "X-Requested-With": "XMLHttpRequest" },
      body: JSON.stringify(datos)
    }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { j._estado = r.status; return j; }); });
  }

  function burbuja(quien, texto) {
    var div = document.createElement("div");
    div.className = "sf-chat-msg sf-chat-" + quien;
    texto.split("\n").forEach(function (linea, i) {
      if (i) { div.appendChild(document.createElement("br")); }
      div.appendChild(document.createTextNode(linea));
    });
    lista.appendChild(div);
    lista.scrollTop = lista.scrollHeight;
    return div;
  }

  function sugerencias(lista_) {
    chips.textContent = "";
    (lista_ || []).forEach(function (s) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "sf-chip"; b.textContent = s;
      b.addEventListener("click", function () { preguntar(s); });
      chips.appendChild(b);
    });
  }

  function acciones(div, r) {
    (r.enlaces || []).forEach(function (e) {
      if (!e.url || e.url.charAt(0) !== "/") { return; }
      var a = document.createElement("a");
      a.href = e.url; a.className = "sf-chat-enlace"; a.textContent = e.texto + " →";
      div.appendChild(a);
    });
    if (!r.id) { return; }
    var pie = document.createElement("div");
    pie.className = "sf-chat-acciones";
    if (r.fuente === "busqueda" || r.fuente === "claude") {
      pie.appendChild(voto(r.id, true)); pie.appendChild(voto(r.id, false));
    }
    if (r.ofrecer_contacto) {
      var c = document.createElement("button");
      c.type = "button"; c.className = "btn btn-sm btn-outline-secondary";
      c.innerHTML = '<i class="bi bi-envelope" aria-hidden="true"></i> Escribir al administrador';
      c.addEventListener("click", function () { formularioContacto(r.id, c); });
      pie.appendChild(c);
    }
    if (pie.children.length) { div.appendChild(pie); }
  }

  function voto(id, util) {
    var b = document.createElement("button");
    b.type = "button"; b.className = "sf-chat-voto";
    b.setAttribute("aria-label", util ? "Me sirvió" : "No me sirvió");
    b.innerHTML = util ? '<i class="bi bi-hand-thumbs-up"></i>' : '<i class="bi bi-hand-thumbs-down"></i>';
    b.addEventListener("click", function () {
      enviarJSON(base + "consulta/" + id + "/calificar/", { util: util });
      var pie = b.parentNode;
      pie.querySelectorAll(".sf-chat-voto").forEach(function (v) { v.remove(); });
      var gracias = document.createElement("small");
      gracias.textContent = util ? "¡Gracias!" : "Gracias. Puede escribirle al administrador.";
      pie.insertBefore(gracias, pie.firstChild);
      if (!util && !pie.querySelector(".btn")) {
        var c = document.createElement("button");
        c.type = "button"; c.className = "btn btn-sm btn-outline-secondary"; c.textContent = "Escribir al administrador";
        c.addEventListener("click", function () { formularioContacto(id, c); });
        pie.appendChild(c);
      }
    });
    return b;
  }

  function formularioContacto(id, disparador) {
    disparador.disabled = true;
    var f = document.createElement("form");
    f.className = "sf-chat-contacto";
    f.innerHTML = '<label class="form-label small mb-1">¿Qué necesita? (opcional)</label>' +
      '<textarea class="form-control form-control-sm mb-2" rows="2" maxlength="1000"></textarea>' +
      (anonimo ? '<label class="form-label small mb-1">Correo o teléfono para responderle</label><input class="form-control form-control-sm mb-2" maxlength="150" required>' : "") +
      '<button class="btn btn-sm btn-sysfood" type="submit">Enviar al administrador</button>';
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      var campo = f.querySelector("input");
      enviarJSON(base + "consulta/" + id + "/contactar/", { mensaje: f.querySelector("textarea").value, contacto: campo ? campo.value : "" })
        .then(function (r) { f.remove(); burbuja("bot", r.texto || r.error || "No se pudo enviar. Intente de nuevo."); if (r.error) { disparador.disabled = false; } })
        .catch(function () { burbuja("bot", "No se pudo enviar. Revise su conexión."); disparador.disabled = false; });
    });
    lista.appendChild(f);
    f.querySelector("textarea").focus();
    lista.scrollTop = lista.scrollHeight;
  }

  function preguntar(texto) {
    texto = (texto || "").trim();
    if (!texto || ocupado) { return; }
    ocupado = true;
    burbuja("yo", texto);
    sugerencias([]);
    var espera = burbuja("bot", "");
    espera.classList.add("sf-chat-escribiendo");
    espera.setAttribute("aria-label", "El asistente está escribiendo");
    enviarJSON(raiz.dataset.preguntar, { pregunta: texto, pagina: location.pathname })
      .then(function (r) {
        espera.remove();
        var div = burbuja("bot", r.texto || "No pude responder en este momento.");
        acciones(div, r);
        sugerencias(r.sugerencias);
      })
      .catch(function () { espera.remove(); burbuja("bot", "No hay conexión con el servidor. Intente de nuevo."); })
      .then(function () { ocupado = false; });
  }

  function abrir() {
    panel.hidden = false;
    boton.setAttribute("aria-expanded", "true");
    raiz.classList.add("abierto");
    entrada.focus();
    if (iniciado) { return; }
    iniciado = true;
    fetch(raiz.dataset.inicio + "?pagina=" + encodeURIComponent(location.pathname), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (r) { burbuja("bot", r.texto); sugerencias(r.sugerencias); })
      .catch(function () { burbuja("bot", "¡Hola! Escriba su pregunta."); });
  }

  function cerrar() {
    panel.hidden = true;
    boton.setAttribute("aria-expanded", "false");
    raiz.classList.remove("abierto");
    boton.focus();
  }

  boton.addEventListener("click", function () { if (panel.hidden) { abrir(); } else { cerrar(); } });
  document.getElementById("sf-chat-cerrar").addEventListener("click", cerrar);
  panel.addEventListener("keydown", function (e) { if (e.key === "Escape") { cerrar(); } });
  document.addEventListener("keydown", function (e) {
    if (e.altKey && (e.key === "a" || e.key === "A")) { e.preventDefault(); if (panel.hidden) { abrir(); } else { cerrar(); } }
  });
  form.addEventListener("submit", function (e) { e.preventDefault(); var t = entrada.value; entrada.value = ""; preguntar(t); });
})();
