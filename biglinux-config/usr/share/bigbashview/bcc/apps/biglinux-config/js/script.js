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
			$.get("/usr/share/bigbashview/bcc/shell/bcfglib.sh", script, function (data) {
				console.log(resp);
				if (data === "#")
					setTimeout(function () {
						$("#modalInfo").show();
					}, 500);
			});
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
			$.get("/usr/share/bigbashview/bcc/shell/bcfglib.sh", script, function (data) {
				console.log(resp);
				if (data === "#")
					setTimeout(function () {
						$("#modalInfo").show();
					}, 500);
			});
		});
	});
});

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

$("#modalOkInfoXFCE").click(function (e) {
	e.preventDefault();
	$("#modalInfoXFCE").hide();
	_run(`qdbus org.kde.ksmserver /KSMServer logout 1 0 2`);
});

$("#modalOkWarningXFCE").click(function (e) {
	e.preventDefault();
	let script = "sh_reset_xfce";
	$(".lds-ring").css("display", "inline-flex");

//	$.get("run/kde.sh", function (data) {
	$.get("/usr/share/bigbashview/bcc/shell/bcfglib.sh", script, function (data) {
		console.log(data);
		if (data === "#") {
			setTimeout(function () {
				$(".lds-ring").css("display", "none");
				$(".modalWarningXFCE").hide();
				$("#modalInfoXFCE").show();
			}, 500);
		}
	});
});
