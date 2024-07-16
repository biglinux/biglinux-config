/*
#  /usr/share/bigbashview/bcc/apps/biglinux-config/js/script.js
#  Description: JS Library for BigLinux Config
#
#  Created: 2024/05/31
#  Altered: 2024/07/14
#
#  Copyright (c) 2023-2024, Vilmar Catafesta <vcatafesta@gmail.com>
#                2020-2023, Bruno Gonçalves <www.biglinux.com.br>
#                2020-2023, Rafael Ruscher <rruscher@gmail.com>
#                2020-2023, eltonff <www.biglinux.com.br>
#  All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions
#  are met:
#  1. Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#  2. Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#
#  THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
#  IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
#  OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
#  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
#  INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
#  NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
#  DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
#  THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
#  THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*/

$(function () {
  $("#Star").trigger("click");
});

/* LEGENDA BOX STATUS BAR */
$(".box-items").mouseover(function () {
  $(this).children("#box-status-bar").css("display", "block");
});

$(".box-items").mouseout(function () {
  $(this).children("#box-status-bar").css("display", "none");
});

/* FIM LEGENDA BOX STATUS BAR */
$(document).on("click", "#point-container", function () {
  var show = $(this).data("show");
  $(show).removeClass("hide").siblings().addClass("hide");
});

$(".search-bar input")
  .focus(function () {
    $(".header").addClass("wide");
  })
  .blur(function () {
    $(".header").removeClass("wide");
  });

$(".dark-light").click(function (e) {
  e.preventDefault();
  var state = $("body").hasClass("light-mode");
  _run("sh_bcfg_setbgcolor " + state);
  console.log("light-mode =:", state);
  $("body").toggleClass("light-mode");
  state = $("body").hasClass("light-mode");
  console.log("light-mode =:", state);
});

var modals = document.getElementsByClassName("modal");
var modalOpenBtn = document.getElementsByClassName("modalOpenBtn");
var currentModal = null;

// Function to open modal by id
function openModal(id) {
  for (i = 0; i < modals.length; i++) {
    if (modals[i].getAttribute("id") == id) {
      currentModal = modals[i];
      $(currentModal).show();
      break;
    }
  }
}

// When the user clicks the button, open modal with the same id
modalOpenBtn.onclick = function () {
  let currentID = modalOpenBtn.getAttribute("id");
  openModal(currentID);
};

// When the user clicks anywhere outside of the modal or the X, close
window.onclick = function (event) {
  if (
    event.target == currentModal ||
    event.target.getAttribute("class") == "modalClose"
  ) {
    $(currentModal).hide();
  }
};

$(document).on("keyup", function (e) {
  if (e.key == "Escape") $(currentModal).hide();
});

$(".restore-skel").on("click", function (e) {
  e.preventDefault();
  let script = $(this).attr("data-value");

  //	$.get("run/" + script, "skel", function (resp) {
  //	$.get("./bcfglib.sh", script, "skel", function (resp) {
  $.get("/usr/share/bigbashview/bcc/shell/bcfglib.sh", script, function (resp) {
    console.log(resp);
    if (resp === "#")
      setTimeout(function () {
        $("#modalInfo").show();
      }, 500);

    if (resp !== "#")
      setTimeout(function () {
        $("#modalWarning").show();
      }, 500);

    $(".modalOkWarning").click(function () {
      _run(`kill -9 ${resp}`);
      $("#modalWarning").hide();

      //			$.get("run/" + script, "skel", function (data) {
      //			$.get("./bcfglib.sh", script, "skel", function (data) {
      $.get(
        "/usr/share/bigbashview/bcc/shell/bcfglib.sh",
        script,
        function (data) {
          console.log(resp);
          if (data === "#")
            setTimeout(function () {
              $("#modalInfo").show();
            }, 500);
        },
      );
    });
  });
});

$(".restore-default").on("click", function (e) {
  e.preventDefault();
  let script = $(this).attr("data-value");

  //	$.get("run/" + script, function (resp) {
  //	$.get("./bcfglib.sh", script, function (resp) {
  $.get("/usr/share/bigbashview/bcc/shell/bcfglib.sh", script, function (resp) {
    console.log(resp);
    if (resp === "#")
      setTimeout(function () {
        $("#modalInfo").show();
      }, 500);

    if (resp !== "#")
      setTimeout(function () {
        $("#modalWarning").show();
      }, 500);

    $(".modalOkWarning").click(function () {
      _run(`kill -9 ${resp}`);
      $("#modalWarning").hide();

      //			$.get("run/" + script, function (data) {
      //			$.get("./bcfglib.sh", script, function (data) {
      $.get(
        "/usr/share/bigbashview/bcc/shell/bcfglib.sh",
        script,
        function (data) {
          console.log(resp);
          if (data === "#")
            setTimeout(function () {
              $("#modalInfo").show();
            }, 500);
        },
      );
    });
  });
});

//#################################################################################################

$("#modalOkWarningKDE").click(function (e) {
  e.preventDefault();
  let script = "sh_reset_kde";
  $(".lds-ring").css("display", "inline-flex");

  //	$.get("run/kde.sh", function (data) {
  $.get("/usr/share/bigbashview/bcc/shell/bcfglib.sh", script, function (data) {
    console.log(data);
    if (data === "#") {
      setTimeout(function () {
        $(".lds-ring").css("display", "none");
        $(".modalWarningKDE").hide();
        $("#modalInfoKDE").show();
      }, 500);
    }
  });
});

$("#modalOkInfoKDE").click(function (e) {
  e.preventDefault();
  $("#modalInfoKDE").hide();
  _run(`qdbus org.kde.ksmserver /KSMServer logout 1 0 2`);
});

$(".modalOkInfo").click(function (e) {
  e.preventDefault();
  $("#modalInfo").hide();
  $(currentModal).hide();
});

$(".modalCancel").click(function (e) {
  e.preventDefault();
  $("#modalWarning").hide();
});

// ##########################################################################################

$("#modalOkWarning").click(function (e) {
  // Previne a ação padrão do elemento (se for um link, por exemplo)
  e.preventDefault();

  // Obtém o valor do atributo data-value do elemento clicado
  let script = $(this).attr("data-value");
  console.log(script);

  // Esconde o modal de aviso
  $(".modalOkWarning").hide();

  // Mostra o indicador de carregamento
  $(".lds-ring").css("display", "inline-flex");

  // Faz uma requisição GET para o script especificado
  $.get("/usr/share/bigbashview/bcc/shell/bcfglib.sh", script, function (data) {
    console.log(data);

    // Verifica se os dados retornados são exatamente "#"
    if (data === "#") {
      // Esconde o indicador de carregamento e mostra o modal de informação após 500ms
      setTimeout(function () {
        $(".lds-ring").css("display", "none");
        $("#modalInfo").show();
      }, 500);
    } else {
      // Esconde o indicador de carregamento e mostra o modal de erro após 500ms
      setTimeout(function () {
        $(".lds-ring").css("display", "none");
        $("#modalErro").show();
      }, 500);
    }
  });
});

// ##########################################################################################

$(".modalClose").click(function (e) {
  e.preventDefault();
//  $("#modalInfo").hide();
//	var modalAtual = getCurrentModal();
//  $(modalAtual).hide();
	$(getCurrentModal()).hide();
});

$("#modalErro").click(function (e) {
  e.preventDefault();
  $("#modalErro").hide();
});

$("#modalOkInfo").click(function (e) {
  e.preventDefault();
  let killcmd = $(this).attr("data-value");
  console.log(killcmd);
	$("#modalInfo").hide();
  //  _run(`qdbus org.kde.ksmserver /KSMServer logout 1 0 2`);
  _run(killcmd);
});

$(".modalOkInfo").click(function (e) {
  e.preventDefault();
	$("#modalInfo").hide();
	$(currentModal).hide();
});

$(".modalCancel").click(function (e) {
  e.preventDefault();
  $("#modalWarning").hide();
});

// ##########################################################################################

$(document).ready(function () {
  // Itera sobre todos os quadros que têm a classe box-not-exist
  $(".box-not-exist").each(function () {
    // Desabilita todos os botões dentro do quadro
    $(this).find(".box-geral-button").attr("disabled", "disabled");
  });
});

//#################################################################################################

$(document).ready(function () {
  // Verifica se há algum elemento com a classe box-not-exist
  if ($(".box-not-exist").length) {
    // Altera a cor de fundo e a cor do texto de todos os elementos com a classe status-bar dentro da div box-not-exist
    $(".box-not-exist #tit-status-bar").css({
      "background-color": "#FF0000", // Vermelho
      color: "#FFFFFF", // Branco
    });
  }
});

//#################################################################################################

function getCurrentModal() {
  // Seleciona o modal atualmente visível
  var currentModal = $(".modal:visible");

  // Verifica se existe um modal visível
  if (currentModal.length) {
		console.log("Current Modal:", currentModal.attr('id'));
    return currentModal;
  } else {
    return null; // Retorna null se nenhum modal estiver visível
  }
}

//#################################################################################################
