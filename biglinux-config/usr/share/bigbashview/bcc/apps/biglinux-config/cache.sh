#!/usr/bin/env bash
# PKG=(1ºNome 2ºScript 3ºCategoria 4ºÍcone 5ºPacote)
#OBS.:Entre colunas separado por espaço e nome separado por hífen
#Desenvolvido por eltonff <https://www.biglinux.com.br> Setembro/2020

#Translation
export TEXTDOMAINDIR="/usr/share/locale"
export TEXTDOMAIN=biglinux-config

PKG=(
"Biglinux-KDE kde.sh System kde.png plasmashell"
"Brave brave.sh Internet brave.png brave-browser"
"Chromium chromium.sh Internet chromium.png chromium skel"
$"Músicas-(Clementine) clementine.sh Multimedia clementine.png clementine skel"
"Dolphin dolphin.sh System dolphin.png dolphin skel"
"Firefox firefox.sh Internet firefox.png firefox skel"
"Gimp gimp.sh Graphic gimp.png gimp skel"
"Google-Chrome google-chrome.sh Internet chrome.png google-chrome"
"Gwenview gwenview.sh Graphic gwenview.png gwenview skel"
"Kate kate.sh Office kate.png kate skel"
"Ksnip ksnip.sh Graphic ksnip.png ksnip skel"
"LibreOffice libreoffice.sh Office libreoffice.png libreoffice skel"
"Okular okular.sh Office okular.png okular skel"
"qBittorrent qbittorrent.sh Internet qbittorrent.png qbittorrent skel"
"Terminal-(Konsole) konsole.sh System konsole.png konsole skel"
$"Vídeos-(Smplayer) smplayer.sh Multimedia smplayer.png smplayer skel"
)

number_modal=0
CLOSE=$"Fechar"

NAME_RESET_BIG=$"Restaurar no modo padrão da distribuição"
COMMENT_RESET_BIG=$"Essa opção restaura o programa com o padrão do BigLinux."
ICON_RESET_BIG="icons/biglinux.png"

ICON_RESET_DEFAULT="icons/default.png"

mkdir -p ~/.bigconfig
[ -e ~/.bigconfig/modal.htm ] && rm ~/.bigconfig/modal.htm

for i in "${PKG[@]}"; do

EXEC="$(cut -d' ' -f5 <<< $i)"

if [ "$(type -p $EXEC)" ];then
  NAME="$(cut -d' ' -f1 <<< $i|tr '-' ' ')"
  SCRIPT="$(cut -d' ' -f2 <<< $i)"
  if [ "$SCRIPT" = "kde.sh" ];then
  		NAME_RESET_DEFAULT=$"Restaurar no modo padrão da distribuição"
  		COMMENT_RESET_DEFAULT=$"Essa opção restaura o programa com o padrão do BigLinux."
  else
  		NAME_RESET_DEFAULT=$"Restaurar no modo padrão do programa"
		COMMENT_RESET_DEFAULT=$"Essa opção restaura o programa com o padrão do desenvolvedor."

  fi
  CATEGORY="$(cut -d' ' -f3 <<< $i)"
  ICON="icons/$(cut -d' ' -f4 <<< $i)"
  HEADER=$"Clique na opção abaixo para restaurar as configurações do programa:"
  SKEL="$(cut -d' ' -f6 <<< $i)"

echo "<!-------------------- $NAME ------------------------------------------------>
<div class=\"col-md-2 waves-effect waves-light box $CATEGORY\">
    <a href=\"#modal$number_modal\" class=\"with-gap modal-trigger\">
    <p class=\"name\"><img src=\"$ICON\" width=38 height=38> $NAME</p></a>
</div>

<!-- Modal Structure -->
<div id=\"modal$number_modal\" class=\"modal\">
    <div class=\"modal-content\">
        <div class=\"center name\">$HEADER</div>
" >> ~/.bigconfig/modal.htm

if [ "$SKEL" ]; then
echo "  <div class=\"col-md-modal waves-effect waves-light\">
            <a onclick=\"_run('run/$SCRIPT 1')\" class=\"tooltipped with-gap\"
               data-position=\"top\" data-delay=\"50\" data-tooltip=\"$COMMENT_RESET_BIG\">
            <p class=\"name\"><img src=\"$ICON_RESET_BIG\" width=38 height=38> $NAME_RESET_BIG</p></a>
        </div>
" >> ~/.bigconfig/modal.htm
fi

echo "  <div class=\"col-md-modal waves-effect waves-light\">
            <a onclick=\"_run('run/$SCRIPT')\" class=\"tooltipped with-gap\"
               data-position=\"top\" data-delay=\"50\" data-tooltip=\"$COMMENT_RESET_DEFAULT\">
            <p class=\"name\"><img src=\"$ICON_RESET_DEFAULT\" width=38 height=38> $NAME_RESET_DEFAULT</p></a>
        </div>
    </div>
    <div class=\"modal-footer\">
      <a href=\"#!\" class=\"modal-close waves-effect waves-green btn-flat\">$CLOSE</a>
    </div>
</div>
" >> ~/.bigconfig/modal.htm

number_modal=$((number_modal+1))
fi

done &
exit
