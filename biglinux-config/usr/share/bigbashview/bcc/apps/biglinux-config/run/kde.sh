#!/usr/bin/env bash

#Translation
export TEXTDOMAINDIR="/usr/share/locale"
export TEXTDOMAIN=biglinux-config

windowID="$(xprop -root '\t$0' _NET_ACTIVE_WINDOW | cut -f 2)"

kdialog --attach="$windowID" --title $"Restaurar Configurações" --icon "configure" \
--yesno $"Você tem certeza que deseja restaurar todas as configurações do KDE/Plasma?\nIsso apagará todas as configurações definidas por $USER!"

RET="$?"
if [ "$RET" != "0" ]; then
        exit
else
        #Kill plasma, kwin and dolphin
        [ "$(pidof dolphin)" != "" ] && killall dolphin
        killall kwin_x11
        killall plasmashell-fix
        killall kwin_x11.orig
        killall plasmashell

        #Remove(home) folders
        rm -r ~/.cache/*
        rm -r ~/.config/dconf
        rm -r ~/.config/fontconfig
        rm -r ~/.config/gtk-2.0
        rm -r ~/.config/gtk-3.0
        rm -r ~/.config/KDE
        rm -r ~/.config/kde.org
        rm -r ~/.config/kdeconnect
        rm -r ~/.config/plasma-workspace
        rm -r ~/.config/psd
        rm -r ~/.config/pulse
        rm -r ~/.config/qtcurve
        rm -r ~/.kde
        rm -r ~/.kdebiglinux
        rm -r ~/.local/share/kactivitymanagerd
        rm -r ~/.local/share/kcookiejar
        rm -r ~/.local/share/kded5
        rm -r ~/.local/share/kded5/keyboard
        rm -r ~/.local/share/kdevappwizard
        rm -r ~/.local/share/kdevelop
        rm -r ~/.local/share/kdevfiletemplates
        rm -r ~/.local/share/kdevscratchpad
        rm -r ~/.local/share/klipper
        rm -r ~/.local/share/knewstuff3
        rm -r ~/.local/share/konsole
        rm -r ~/.local/share/kscreen
        rm -r ~/.local/share/kservices5
        rm -r ~/.local/share/ksysguard
        rm -r ~/.local/share/ktexteditor_snippets
        rm -r ~/.local/share/kwalletd
        rm -r ~/.local/share/kxmlgui5
        rm -r ~/.local/share/plasma_icons

        #Remove(home) files
        rm ~/.bash_aliases
        rm ~/.bash_history
        rm ~/.bash_logout
        rm ~/.bashrc
        rm ~/.big_desktop_theme
        rm ~/.gtkrc-2.0
        rm ~/.profile
        rm ~/.config/akregatorrc
        rm ~/.config/arkrc
        rm ~/.config/baloofileinformationrc
        rm ~/.config/baloofilerc
        rm ~/.config/bluedevilglobalrc
        rm ~/.config/breezerc
        rm ~/.config/drkonqirc
        rm ~/.config/gtkrc
        rm ~/.config/gtkrc-2.0
        rm ~/.config/kactivitymanagerd-statsrc
        rm ~/.config/kactivitymanagerd-switcher
        rm ~/.config/kactivitymanagerdrc
        rm ~/.config/kcm_touchpad.notifyrc
        rm ~/.config/kcminputrc
        rm ~/.config/kconf_updaterc
        rm ~/.config/kded5rc
        rm ~/.config/kded_device_automounterrc
        rm ~/.config/kdeglobals
        rm ~/.config/kdeveloprc
        rm ~/.config/kdialogrc
        rm ~/.config/kfindrc
        rm ~/.config/kgammarc
        rm ~/.config/kglobalshortcutsrc
        rm ~/.config/khotkeysrc
        rm ~/.config/kiorc
        rm ~/.config/klaunchrc
        rm ~/.config/klipperrc
        rm ~/.config/kmenueditrc
        rm ~/.config/kmixrc
        rm ~/.config/konsole.knsrc
        rm ~/.config/konsolerc
        rm ~/.config/kpatrc
        rm ~/.config/krunnerrc
        rm ~/.config/kscreenlockerrc
        rm ~/.config/kservicemenurc
        rm ~/.config/ksmserverrc
        rm ~/.config/ksplashrc
        rm ~/.config/ksysguardrc
        rm ~/.config/ktimezonedrc
        rm ~/.config/kwalletrc
        rm ~/.config/kwinqtcurverc
        rm ~/.config/kwinrc
        rm ~/.config/kwinrulesrc
        rm ~/.config/kxkbrc
        rm ~/.config/plasma-localerc
        rm ~/.config/plasma-nm
        rm ~/.config/plasma-org.kde.plasma.desktop-appletsrc
        rm ~/.config/plasma.emojierrc
        rm ~/.config/plasma_calendar_holiday_regions
        rm ~/.config/plasma_workspace.notifyrc
        rm ~/.config/plasmanotifyrc
        rm ~/.config/plasmarc
        rm ~/.config/plasmashellrc
        rm ~/.config/plasmavaultrc
        rm ~/.config/plasmawindowed-appletsrc
        rm ~/.config/plasmawindowedrc
        rm ~/.config/powerdevil.notifyrc
        rm ~/.config/powerdevilrc
        rm ~/.config/powermanagementprofilesrc
        rm ~/.config/spectaclerc
        rm ~/.config/systemmonitorrc
        rm ~/.config/systemsettingsrc
        rm ~/.config/touchpadrc
        rm ~/.config/touchpadxlibinputrc
        rm ~/.config/Trolltech.conf
        rm ~/.config/xdg-desktop-portal-kderc
        rm ~/.local/share/RecentDocuments/*

        #Copy(skel) folders
        cp -r /etc/skel/.config/dconf ~/.config/dconf
        cp -r /etc/skel/.config/fontconfig ~/.config/fontconfig
        cp -r /etc/skel/.config/gtk-3.0 ~/.config/gtk-3.0
        cp -r /etc/skel/.config/psd ~/.config/psd
        cp -r /etc/skel/.config/pulse ~/.config/pulse
        cp -r /etc/skel/.config/qtcurve ~/.config/qtcurve
        cp -r /etc/skel/.kde ~/.kde
        cp -r /etc/skel/.kdebiglinux ~/.kdebiglinux
        cp -r /etc/skel/.local/share/kactivitymanagerd ~/.local/share/kactivitymanagerd
        cp -r /etc/skel/.local/share/konsole ~/.local/share/konsole
        cp -r /etc/skel/.local/share/kxmlgui5 ~/.local/share/kxmlgui5

        #Copy(skel) files
        cp /etc/skel/.bash_aliases ~/.bash_aliases
        cp /etc/skel/.bash_logout ~/.bash_logout
        cp /etc/skel/.bashrc ~/.bashrc
        cp /etc/skel/.gtkrc-2.0 ~/.gtkrc-2.0
        cp /etc/skel/.profile ~/.profile
		cp /etc/skel/.config/breezerc ~/.config/breezerc
        cp /etc/skel/.config/baloofilerc ~/.config/baloofilerc
        cp /etc/skel/.config/gtkrc ~/.config/gtkrc
        cp /etc/skel/.config/gtkrc-2.0 ~/.config/gtkrc-2.0
        cp /etc/skel/.config/kactivitymanagerd-statsrc ~/.config/kactivitymanagerd-statsrc
        cp /etc/skel/.config/kactivitymanagerdrc ~/.config/kactivitymanagerdrc
        cp /etc/skel/.config/kcm_touchpad.notifyrc ~/.config/kcm_touchpad.notifyrc
        cp /etc/skel/.config/kcminputrc ~/.config/kcminputrc
        cp /etc/skel/.config/kded5rc ~/.config/kded5rc
        cp /etc/skel/.config/kded_device_automounterrc ~/.config/kded_device_automounterrc
        cp /etc/skel/.config/kdeglobals ~/.config/kdeglobals
        cp /etc/skel/.config/kglobalshortcutsrc ~/.config/kglobalshortcutsrc
        cp /etc/skel/.config/khotkeysrc ~/.config/khotkeysrc
        cp /etc/skel/.config/kiorc ~/.config/kiorc
        cp /etc/skel/.config/klaunchrc ~/.config/klaunchrc
        cp /etc/skel/.config/konsole.knsrc ~/.config/konsole.knsrc
        cp /etc/skel/.config/konsolerc ~/.config/konsolerc
        cp /etc/skel/.config/kpatrc ~/.config/kpatrc
        cp /etc/skel/.config/krunnerrc ~/.config/krunnerrc
        cp /etc/skel/.config/kscreenlockerrc ~/.config/kscreenlockerrc
        cp /etc/skel/.config/kservicemenurc ~/.config/kservicemenurc
        cp /etc/skel/.config/ksmserverrc ~/.config/ksmserverrc
        cp /etc/skel/.config/ksplashrc ~/.config/ksplashrc
        cp /etc/skel/.config/kwinqtcurverc ~/.config/kwinqtcurverc
        cp /etc/skel/.config/kwinrc ~/.config/kwinrc
        cp /etc/skel/.config/kwinrulesrc ~/.config/kwinrulesrc
        cp /etc/skel/.config/plasma-org.kde.plasma.desktop-appletsrc ~/.config/plasma-org.kde.plasma.desktop-appletsrc
        cp /etc/skel/.config/plasma_workspace.notifyrc ~/.config/plasma_workspace.notifyrc
        cp /etc/skel/.config/plasmarc ~/.config/plasmarc
        cp /etc/skel/.config/plasmashellrc ~/.config/plasmashellrc
        cp /etc/skel/.config/powerdevil.notifyrc ~/.config/powerdevil.notifyrc
        cp /etc/skel/.config/spectaclerc ~/.config/spectaclerc
        cp /etc/skel/.config/touchpadrc ~/.config/touchpadrc
        cp /etc/skel/.config/Trolltech.conf ~/.config/Trolltech.conf

        #Default theme
        first-login-theme

        #Compositing mode - based on biglinux-themes
        MODE="$(<$HOME/.big_performance)"
        if [ "$MODE" = "0" ];then
                # Animation 0
                kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key AnimationSpeed 3
                kwriteconfig5 --file ~/.config/kdeglobals --group KDE --key AnimationDurationFactor ""

                # Composition on
                kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key Enabled true

                # Opengl 2
                kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key GLCore false
                kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key Backend OpenGL

        elif [ "$MODE" = "1" ];then
                # Animation 2
                kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key AnimationSpeed 1
                kwriteconfig5 --file ~/.config/kdeglobals --group KDE --key AnimationDurationFactor 0.5

                # Composition on
                kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key Enabled true

                # Opengl 2
                kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key GLCore false
                kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key Backend OpenGL

        else
                # Animation 0
                kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key AnimationSpeed 2
                kwriteconfig5 --file ~/.config/kdeglobals --group KDE --key AnimationDurationFactor 0.08838834764831843

                # XRender
                kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key Backend XRender
        fi

        #Reopen plasma and kwin
        plasmashell-fix 2> /dev/null &
        kwin_x11 2> /dev/null &

        sleep 3
        kdialog --attach="$windowID" --title $"Restaurar Configurações" --icon "configure" \
                --msgbox $"As configurações foram restauradas com sucesso!\nÉ necessário fazer logoff/login para concluir a restauração!"

fi
exit
