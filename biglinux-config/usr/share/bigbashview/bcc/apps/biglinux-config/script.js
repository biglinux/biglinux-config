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

//$(function () {
//  $(".menu-link").click(function () {
//    $(".menu-link").removeClass("is-active");
//    $(this).addClass("is-active");
//  });
//});
//
//$(function () {
//  $(".main-header-link").click(function () {
//    $(".main-header-link").removeClass("is-active");
//    $(this).addClass("is-active");
//  });
//});
//
//const dropdowns = document.querySelectorAll(".dropdown");
//dropdowns.forEach((dropdown) => {
//  dropdown.addEventListener("click", (e) => {
//    e.stopPropagation();
//    dropdowns.forEach((c) => c.classList.remove("is-active"));
//    dropdown.classList.add("is-active");
//  });
//});

$(".search-bar input")
  .focus(function () {
    $(".header").addClass("wide");
  })
  .blur(function () {
    $(".header").removeClass("wide");
  });

const toggleButton = document.querySelector(".dark-light");

toggleButton.addEventListener("click", () => {
  document.body.classList.toggle("light-mode");
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
modalOpenBtn.onclick = function() {
  let currentID = modalOpenBtn.getAttribute("id");
  openModal(currentID);
}

// When the user clicks anywhere outside of the modal or the X, close
window.onclick = function(event) {
  if (event.target == currentModal || event.target.getAttribute("class") == "modalClose") {
    $(currentModal).hide();
  }
}


$(document).on("keyup", function(e) {
  if (e.key == "Escape") $(currentModal).hide();
});


$(".restore-skel").on("click",function(){
  let script = $(this).attr("data-value");

  $.get("run/"+script, "skel", function(resp){
    if(resp==="#") setTimeout(function(){$("#modalInfo").show()}, 500);

    if(resp!=="#") setTimeout(function(){$("#modalWarning").show()}, 500);

    $(".modalOkWarning").click(function(){
      _run(`kill -9 ${resp}`);
      $("#modalWarning").hide();

      $.get("run/"+script, "skel", function(data){
        if(data==="#") setTimeout(function(){$("#modalInfo").show()}, 500);
      });

    });
  });
});


$(".restore-default").on("click",function(){
  let script = $(this).attr("data-value");

  $.get("run/"+script, function(resp){
    if(resp==="#") setTimeout(function(){$("#modalInfo").show()}, 500);

    if(resp!=="#") setTimeout(function(){$("#modalWarning").show()}, 500);

    $(".modalOkWarning").click(function(){
      _run(`kill -9 ${resp}`);
      $("#modalWarning").hide();

      $.get("run/"+script, function(data){
        if(data==="#") setTimeout(function(){$("#modalInfo").show()}, 500);
      });

    });
  });
});


$(".restore-default-kde").on("click", function(){
  $("#modalWarningKDE").show();

  $(".modalOkWarningKDE").click(function(){
    $("#modalWarningKDE").hide();

    $.get("run/kde.sh", function(data){
      if(data==="#") setTimeout(function(){$("#modalInfoKDE").show()}, 500);
    });

  });
});


$(".modalOkInfo").click(function(){
  $("#modalInfo").hide();
  $("#modalInfoKDE").hide();
  $(currentModal).hide();
});


$(".modalCancel").click(function(){
  $("#modalWarning").hide();
  $("#modalWarningKDE").hide();
});
