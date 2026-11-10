/* Mapa de beneficiarios: marcadores agrupados y mapa de calor (Leaflet, local).
   Solo se usa en páginas del administrador. */
(function () {
  "use strict";

  function escapar(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function numero(v) { return Number(v).toLocaleString("es-CO", { maximumFractionDigits: 1 }); }

  function capaBase(cfg) {
    return L.tileLayer(cfg.tiles, { maxZoom: 19, attribution: escapar(cfg.atribucion) });
  }

  window.sfMapa = function (id, opciones) {
    var contenedor = document.getElementById(id);
    if (!contenedor || !window.L) { return null; }
    var cfg = opciones.config;
    var mapa = L.map(contenedor, { scrollWheelZoom: !opciones.compacto, zoomControl: true }).setView(cfg.centro, cfg.zoom);
    capaBase(cfg).addTo(mapa);

    var grupos = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 45 });
    var calor = L.heatLayer([], { radius: 30, blur: 24, maxZoom: 16, max: 1, minOpacity: 0.25,
      gradient: { 0.2: "#5ec28a", 0.45: "#ffc83d", 0.7: "#ff8a3d", 1: "#b42318" } });
    grupos.addTo(mapa);
    if (opciones.calorInicial !== false) { calor.addTo(mapa); }
    L.control.layers(null, { "Marcadores agrupados": grupos, "Mapa de calor (necesidad)": calor }, { collapsed: !!opciones.compacto }).addTo(mapa);

    var estado = document.createElement("div");
    estado.className = "sf-mapa-estado";
    estado.setAttribute("role", "status");
    estado.setAttribute("aria-live", "polite");
    contenedor.appendChild(estado);

    function aviso(texto, cargando) {
      estado.innerHTML = cargando ? '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>' + escapar(texto) : escapar(texto);
      estado.hidden = !texto;
    }

    function cargar(parametros) {
      aviso("Cargando ubicaciones…", true);
      contenedor.classList.add("sf-cargando-mapa");
      var url = opciones.datosUrl + (parametros ? "?" + parametros : "");
      return fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
        .then(function (r) { if (!r.ok) { throw new Error(r.status); } return r.json(); })
        .then(function (datos) {
          grupos.clearLayers();
          var puntosCalor = [], limites = [];
          datos.puntos.forEach(function (p) {
            var marca = L.circleMarker([p.lat, p.lng], { radius: 8, color: "#fff", weight: 2, fillColor: p.color, fillOpacity: 0.95 });
            marca.bindPopup(
              '<strong>' + escapar(p.nombre) + '</strong><br>' +
              '<span class="badge" style="background:' + escapar(p.color) + ';color:#fff">' + escapar(p.grupo) + '</span> ' +
              'puntaje <b>' + numero(p.puntaje) + '</b><br>' +
              escapar(p.personas) + ' persona(s) · ' + escapar(p.solicitudes) + ' solicitud(es)<br>' +
              (p.zona ? 'Zona: ' + escapar(p.zona) + '<br>' : '') +
              'Verificación: ' + escapar(p.verif) + '<br>' +
              '<a href="' + escapar(p.url) + '">Ver beneficiario</a>'
            );
            grupos.addLayer(marca);
            puntosCalor.push([p.lat, p.lng, p.peso]);
            limites.push([p.lat, p.lng]);
          });
          var maximo = puntosCalor.reduce(function (m, p) { return Math.max(m, p[2]); }, 0);
          calor.setOptions({ max: Math.max(0.35, maximo * 0.8) });
          calor.setLatLngs(puntosCalor);
          if (limites.length && opciones.ajustar !== false) { mapa.fitBounds(limites, { padding: [30, 30], maxZoom: 15 }); }
          aviso(datos.total ? "" : "No hay beneficiarios ubicados con estos filtros.");
          if (opciones.total) { opciones.total.textContent = datos.total; }
        })
        .catch(function () { aviso("No se pudieron cargar las ubicaciones. Intente de nuevo."); })
        .finally(function () { contenedor.classList.remove("sf-cargando-mapa"); });
    }

    if (opciones.leyenda && opciones.leyenda.length) {
      var leyenda = L.control({ position: "bottomright" });
      leyenda.onAdd = function () {
        var div = L.DomUtil.create("div", "sf-mapa-leyenda");
        div.innerHTML = "<strong>Grupo de necesidad</strong>" + opciones.leyenda.map(function (g) {
          return '<div><span style="background:' + escapar(g.color) + '"></span>' + escapar(g.nombre) + "</div>";
        }).join("") + '<div class="mt-1"><span class="sf-calor-muestra"></span>Calor: necesidad concentrada</div>';
        return div;
      };
      leyenda.addTo(mapa);
    }

    var formulario = opciones.formulario && document.getElementById(opciones.formulario);
    function consulta() {
      if (!formulario) { return opciones.consulta || ""; }
      return new URLSearchParams(new FormData(formulario)).toString();
    }
    if (formulario) {
      formulario.addEventListener("submit", function (e) {
        e.preventDefault();
        var q = consulta();
        history.replaceState(null, "", "?" + q);
        document.querySelectorAll("[data-exportar-mapa]").forEach(function (a) { a.href = a.dataset.base + "?" + q; });
        cargar(q);
      });
      document.querySelectorAll("[data-exportar-mapa]").forEach(function (a) { a.href = a.dataset.base + "?" + consulta(); });
    }
    cargar(consulta());
    setTimeout(function () { mapa.invalidateSize(); }, 200);
    return { mapa: mapa, recargar: function () { return cargar(consulta()); } };
  };

  /* Mapa pequeño de un beneficiario: muestra su punto y permite elegir otro con un clic. */
  window.sfMapaPunto = function (id, cfg, punto, campos) {
    var contenedor = document.getElementById(id);
    if (!contenedor || !window.L) { return; }
    var centro = punto || cfg.centro;
    var mapa = L.map(contenedor).setView(centro, punto ? 16 : cfg.zoom);
    capaBase(cfg).addTo(mapa);
    var marca = punto ? L.marker(punto).addTo(mapa) : null;
    mapa.on("click", function (e) {
      if (!campos) { return; }
      var lat = e.latlng.lat.toFixed(6), lng = e.latlng.lng.toFixed(6);
      document.getElementById(campos.lat).value = lat;
      document.getElementById(campos.lng).value = lng;
      if (marca) { marca.setLatLng(e.latlng); } else { marca = L.marker(e.latlng).addTo(mapa); }
    });
    setTimeout(function () { mapa.invalidateSize(); }, 200);
  };
})();
