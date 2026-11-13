/* Página de inicio: profundidad de la portada y caja de donación en 3D.
   Sin librerías: transformaciones CSS 3D y requestAnimationFrame. Con «reducir movimiento»
   no hay seguimiento del mouse ni giro automático; los pasos siguen cambiando la cara visible. */
(function () {
  "use strict";
  var reducir = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var punteroFino = window.matchMedia("(pointer: fine)").matches;

  function acercar(actual, objetivo, factor) { return actual + (objetivo - actual) * factor; }
  function limitar(v, min, max) { return Math.max(min, Math.min(max, v)); }

  /* ---------- 1. Portada: la foto y el texto se mueven a distinta velocidad ---------- */
  var portada = document.querySelector(".pt-masthead");
  if (portada && !reducir && punteroFino) {
    var foto = portada.querySelector(".pt-masthead-foto");
    var texto = portada.querySelector(".pt-masthead-texto");
    var px = 0, py = 0, cx = 0, cy = 0, enCurso = false;

    var moverPortada = function () {
      cx = acercar(cx, px, 0.08);
      cy = acercar(cy, py, 0.08);
      foto.style.transform = "translate3d(" + (-cx * 30).toFixed(2) + "px," + (-cy * 22).toFixed(2) + "px,0)";
      texto.style.transform = "translate3d(" + (cx * 12).toFixed(2) + "px," + (cy * 8).toFixed(2) + "px,0)";
      if (Math.abs(px - cx) > 0.001 || Math.abs(py - cy) > 0.001) {
        window.requestAnimationFrame(moverPortada);
      } else {
        enCurso = false;
      }
    };
    var pedirPortada = function () {
      if (!enCurso) { enCurso = true; window.requestAnimationFrame(moverPortada); }
    };
    portada.addEventListener("pointermove", function (e) {
      var r = portada.getBoundingClientRect();
      px = (e.clientX - r.left) / r.width - 0.5;
      py = (e.clientY - r.top) / r.height - 0.5;
      pedirPortada();
    });
    portada.addEventListener("pointerleave", function () { px = 0; py = 0; pedirPortada(); });
  }

  /* ---------- 2. Caja de donación: cada cara lateral es un paso ---------- */
  var escena = document.querySelector(".pt-caja-escena");
  if (!escena) { return; }
  var caja = escena.querySelector(".pt-caja");
  var sombra = escena.querySelector(".pt-caja-sombra");
  var caras = Array.prototype.slice.call(caja.querySelectorAll(".pt-cara")).slice(0, 4);
  var botones = Array.prototype.slice.call(document.querySelectorAll(".pt-paso"));
  var INCLINACION = -20;          // vista desde arriba para que se vea la tapa
  var actual = 0;                 // paso visible
  var giroBase = 0;               // ángulo acumulado (múltiplos de 90)
  var arrastre = 0;               // grados mientras se arrastra
  var mx = 0, my = 0;             // posición del mouse respecto a la caja (-1 a 1)
  var giroY = 0, giroX = INCLINACION;
  var visible = false, tocada = false, arrastrando = false, inicioX = 0, inicioY = 0;

  function marcarBotones() {
    botones.forEach(function (b, i) { b.setAttribute("aria-pressed", i === actual ? "true" : "false"); });
  }

  // Gira por el camino más corto hasta la cara del paso «i».
  function elegir(i) {
    var diferencia = ((i - actual) % 4 + 4) % 4;
    if (diferencia === 3) { diferencia = -1; }
    giroBase -= diferencia * 90;
    actual = i;
    marcarBotones();
    if (reducir) { pintar(true); }
  }

  // Luz frontal: cada cara se oscurece según cuánto se aleja de mirar al frente.
  function iluminar(y) {
    caras.forEach(function (cara, i) {
      var angulo = (y + i * 90) * Math.PI / 180;
      var luz = (Math.cos(angulo) + 1) / 2;           // 1 de frente, 0 de espaldas
      cara.style.setProperty("--sombra", (0.42 * (1 - luz)).toFixed(3));
    });
  }

  function pintar(inmediato) {
    var objetivoY = giroBase + arrastre + (reducir ? 0 : mx * 28);
    var objetivoX = INCLINACION + (reducir ? 0 : -my * 14);
    if (inmediato) {
      giroY = objetivoY; giroX = objetivoX;
    } else {
      giroY = acercar(giroY, objetivoY, arrastrando ? 0.35 : 0.09);
      giroX = acercar(giroX, objetivoX, 0.09);
    }
    caja.style.transform = "rotateX(" + giroX.toFixed(2) + "deg) rotateY(" + giroY.toFixed(2) + "deg)";
    sombra.style.transform = "translateX(" + (Math.sin(giroY * Math.PI / 180) * 10).toFixed(2) + "px) scale(" + (1 + (giroX - INCLINACION) / 80).toFixed(3) + ")";
    iluminar(giroY);
  }

  function animar() {
    if (!visible) { return; }
    pintar(false);
    window.requestAnimationFrame(animar);
  }

  // La caja «mira» hacia el mouse en cualquier parte de la pantalla.
  if (!reducir && punteroFino) {
    window.addEventListener("pointermove", function (e) {
      if (!visible || arrastrando) { return; }
      var r = escena.getBoundingClientRect();
      mx = limitar((e.clientX - (r.left + r.width / 2)) / (window.innerWidth / 2), -1, 1);
      my = limitar((e.clientY - (r.top + r.height / 2)) / (window.innerHeight / 2), -1, 1);
    }, { passive: true });
  }

  // Arrastrar con mouse o con el dedo; al soltar, se acomoda en la cara más cercana.
  escena.addEventListener("pointerdown", function (e) {
    arrastrando = true; tocada = true;
    inicioX = e.clientX; inicioY = e.clientY;
    escena.setPointerCapture(e.pointerId);
    escena.classList.add("arrastrando");
  });
  escena.addEventListener("pointermove", function (e) {
    if (!arrastrando) { return; }
    arrastre = (e.clientX - inicioX) * 0.6;
    if (reducir) { pintar(true); }
  });
  function soltar() {
    if (!arrastrando) { return; }
    arrastrando = false;
    escena.classList.remove("arrastrando");
    giroBase = Math.round((giroBase + arrastre) / 90) * 90;
    arrastre = 0;
    actual = ((-giroBase / 90) % 4 + 4) % 4;
    marcarBotones();
    if (reducir) { pintar(true); }
  }
  escena.addEventListener("pointerup", soltar);
  escena.addEventListener("pointercancel", soltar);

  botones.forEach(function (b, i) {
    b.addEventListener("click", function () { tocada = true; elegir(i); });
    b.addEventListener("mouseenter", function () { tocada = true; elegir(i); });
  });

  // Solo se anima mientras la sección está en pantalla.
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entradas) {
      var antes = visible;
      visible = entradas[0].isIntersecting;
      if (visible && !antes && !reducir) { window.requestAnimationFrame(animar); }
    }, { threshold: 0.15 }).observe(escena);
  } else {
    visible = true;
    if (!reducir) { window.requestAnimationFrame(animar); }
  }

  // Recorrido automático hasta que la persona interactúe.
  if (!reducir) {
    window.setInterval(function () {
      if (visible && !tocada && !arrastrando && !document.hidden) { elegir((actual + 1) % 4); }
    }, 3800);
  }

  pintar(true);
})();
