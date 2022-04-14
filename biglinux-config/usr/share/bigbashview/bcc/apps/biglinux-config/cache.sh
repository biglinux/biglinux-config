#!/usr/bin/env bash

##################################
#  Author Create: eltonff (www.biglinux.com.br) 
#  Author Modify: Rafael Ruscher (rruscher@gmail.com)
#  Create Date:    2020/09/01 
#  Modify Date:    2022/03/01 
#  
#  Description: Restore Default to help usage of BigLinux 
#  
# Licensed by GPL V2 or greater
##################################
# PKG=(1ºNome 2ºScript 3ºCategoria 4ºÍcone 5ºPacote)
#OBS.:Entre colunas separado por espaço e nome separado por hífen

#Translation
export TEXTDOMAINDIR="/usr/share/locale"
export TEXTDOMAIN=biglinux-config

COMMENT_skel=$"Restaurar&nbsp;o&nbsp;programa&nbsp;como&nbsp;modo&nbsp;padrão&nbsp;ou&nbsp;distribuição&nbsp;BigLinux."
COMMENT_normal=$"Restaurar&nbsp;o&nbsp;programa&nbsp;como&nbsp;modo&nbsp;padrão."

PKG=(
"Biglinux-KDE kde.sh Star kde.png plasmashell  $COMMENT_normal"
"Brave brave.sh Star brave.png brave-browser  $COMMENT_normal"
"Firefox firefox.sh Star firefox.png firefox skel $COMMENT_skel"
"Dolphin dolphin.sh Star dolphin.png dolphin skel $COMMENT_skel"
"Kate kate.sh Star kate.png kate skel $COMMENT_skel"
"Biglinux-KDE kde.sh System kde.png plasmashell  $COMMENT_normal"
"Brave brave.sh Internet brave.png brave-browser  $COMMENT_normal"
"Chromium chromium.sh Internet chromium.png chromium skel $COMMENT_skel"
$"Músicas-(Clementine) clementine.sh Multimedia clementine.png clementine skel $COMMENT_skel"
$"Gravador-de-Tela-(vokoscreenNG) vokoscreen.sh Multimedia vokoscreen.png vokoscreenNG  $COMMENT_normal"
"Dolphin dolphin.sh System dolphin.png dolphin skel $COMMENT_skel"
"Firefox firefox.sh Internet firefox.png firefox skel $COMMENT_skel"
"Gimp gimp.sh Graphic gimp.png gimp skel $COMMENT_skel"
"Google-Chrome google-chrome.sh Internet chrome.png google-chrome   $COMMENT_normal"
"Gwenview gwenview.sh Graphic gwenview.png gwenview skel $COMMENT_skel"
"Kate kate.sh Office kate.png kate skel $COMMENT_skel"
"Ksnip ksnip.sh Graphic ksnip.png ksnip skel $COMMENT_skel"
"LibreOffice libreoffice.sh Office libreoffice.png libreoffice skel $COMMENT_skel"
"Okular okular.sh Office okular.png okular skel $COMMENT_skel"
"qBittorrent qbittorrent.sh Internet qbittorrent.png qbittorrent skel $COMMENT_skel"
$"Vídeos-(Smplayer) smplayer.sh Multimedia smplayer.png smplayer skel $COMMENT_skel"
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
  HEADER=$"Restaurar as configurações do programa:"
  SKEL="$(cut -d' ' -f6 <<< $i)"
  COMMENT="$(cut -d' ' -f7 <<< $i)"

  
echo "
<div class=\"box-1 box-2 box-3 box-4 box-5 box-items $CATEGORY\">
    <div id=\"box-status-bar\"><div id=\"tit-status-bar\">$COMMENT</div>
    </div>
    <button onclick=\"openModal('modal_$number_modal')\" id=\"box-subtitle\" class=\"box-geral-icons box-geral-button\">
        <div class=\"box-imagem-icon\"><img class=\"box-imagem-icon\" src=\"$ICON\"></div>
        <div class=\"box-titulo\">$NAME</div>
    </button>
</div>
" >> ~/.bigconfig/modal.htm

# <div class="app-card">
#   <span><svg viewBox="0 0 512 512">
#       <path fill="currentColor" d="M204.3 5C104.9 24.4 24.8 104.3 5.2 203.4c-37 187 131.7 326.4 258.8 306.7 41.2-6.4 61.4-54.6 42.5-91.7-23.1-45.4 9.9-98.4 60.9-98.4h79.7c35.8 0 64.8-29.6 64.9-65.3C511.5 97.1 368.1-26.9 204.3 5zM96 320c-17.7 0-32-14.3-32-32s14.3-32 32-32 32 14.3 32 32-14.3 32-32 32zm32-128c-17.7 0-32-14.3-32-32s14.3-32 32-32 32 14.3 32 32-14.3 32-32 32zm128-64c-17.7 0-32-14.3-32-32s14.3-32 32-32 32 14.3 32 32-14.3 32-32 32zm128 64c-17.7 0-32-14.3-32-32s14.3-32 32-32 32 14.3 32 32-14.3 32-32 32z"></path>
#     </svg>
#     Aparência, desempenho e usabilidade
#   </span>
#   <div class="app-card__subtext">Disponibilizamos configurações completas para você selecionar de forma extremamente simples.</div>
#   <div class="app-card-buttons">
#     <button class="content-button status-button">Abrir</button>
#   </div>
# </div>



echo "
<div id=\"modal_$number_modal\" class=\"modal\">
  <div class=\"modalContent\">
    <div>
      <i style=\"vertical-align: middle; margin-right: 5px;\"><img src=\"$ICON\" width=\"42\" height=\"42\" ></i>$HEADER
    </div>
" >> ~/.bigconfig/modal.htm


if [ "$SKEL" ]; then
echo " 

<div class=\"app-card\" style=\"width: 100%; border: 1px solid #444444; margin: 3px;\" onclick=\"_run('run/$SCRIPT 1')\">
  <span><img src=\"$ICON_RESET_BIG\" width=\"32\" height=\"32\" style=\"margin-right: 10px;\">
    $NAME_RESET_BIG
  </span>
</div>

" >> ~/.bigconfig/modal.htm
fi
echo " 
<div class=\"app-card\" style=\"width: 100%; border: 1px solid #444444; margin: 3px;\" onclick=\"_run('run/$SCRIPT 1')\">
  <span><img src=\"$ICON_RESET_DEFAULT\" width=\"32\" height=\"32\" style=\"margin-right: 10px;\">
    $NAME_RESET_DEFAULT
  </span>
</div>
" >> ~/.bigconfig/modal.htm

echo "
      <div class=\"content-button-wrapper\" style=\"text-align: right;\">
        <button class=\"modalClose\">Fechar</button>
      </div>
  </div>
</div>
" >> ~/.bigconfig/modal.htm

number_modal=$((number_modal+1))
fi

done &
exit
