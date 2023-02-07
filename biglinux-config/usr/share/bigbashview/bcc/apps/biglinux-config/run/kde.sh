#!/usr/bin/env bash

#Kill dolphin
PROG=$(pidof dolphin)
[ -n "$PROG" ] && kill -9 "$PROG"

#Remove(home) folders
rm -r ~/.cache/*
rm -r ~/.config/dconf
rm -r ~/.config/gtk-3.0
rm -r ~/.config/gtk-4.0
rm -r ~/.config/KDE
rm -r ~/.config/kde.org
rm -r ~/.config/kdeconnect
rm -r ~/.config/kdedefaults
rm -r ~/.config/Kvantum
rm -r ~/.config/latte
rm -r ~/.config/pulse
rm -r ~/.kdebiglinux
rm -r ~/.local/share/kactivitymanagerd
rm -r ~/.local/share/kcookiejar
rm -r ~/.local/share/kded5
rm -r ~/.local/share/knewstuff3
rm -r ~/.local/share/konsole
rm -r ~/.local/share/kpeoplevcard
rm -r ~/.local/share/kscreen
rm -r ~/.local/share/ksysguard
rm -r ~/.local/share/kwalletd
rm -r ~/.local/share/kwin
rm -r ~/.local/share/kxmlgui5
rm -r ~/.local/share/plasma_icons
rm -r ~/.local/share/plasma

#Remove(home) files
rm ~/.bash_history
rm ~/.bash_logout
rm ~/.bashrc
rm ~/.bash_profile
rm ~/.big_desktop_theme
rm ~/.big_performance
rm ~/.big_preload
rm ~/.gtkrc-2.0
rm ~/.config/akregatorrc
rm ~/.config/arkrc
rm ~/.config/baloofileinformationrc
rm ~/.config/baloofilerc
rm ~/.config/bluedevilglobalrc
rm ~/.config/breezerc
rm ~/.config/drkonqirc
rm ~/.config/gtkrc
rm ~/.config/gtkrc-2.0
rm ~/.config/latte
rm ~/.config/kactivitymanagerdrc
rm ~/.config/kcminputrc
rm ~/.config/kconf_updaterc
rm ~/.config/kded5rc
rm ~/.config/kdeglobals
rm ~/.config/kdialogrc
rm ~/.config/kfontinstuirc
rm ~/.config/kgammarc
rm ~/.config/kglobalshortcutsrc
rm ~/.config/khotkeysrc
rm ~/.config/kiorc
rm ~/.config/klaunchrc
rm ~/.config/klassyrc
rm ~/.config/kmenueditrc
rm ~/.config/kmixrc
rm ~/.local/share/krunnerstaterc
rm ~/.config/kscreenlockerrc
rm ~/.config/kservicemenurc
rm ~/.config/ksmserverrc
rm ~/.config/ksplashrc
rm ~/.config/ksysguardrc
rm ~/.config/ktimezonedrc
rm ~/.config/kwalletrc
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
rm ~/.config/Trolltech.conf
rm ~/.config/xdg-desktop-portal-kderc
rm ~/.local/share/RecentDocuments/*
rm ~/.local/share/Trash/files/*

#Copy(skel) folders
cp -rf /etc/skel/.config ~
cp -rf /etc/skel/.local ~
cp -rf /etc/skel/.pje ~
cp -rf /etc/skel/.pki ~

#Copy(skel) files
cp -f /etc/skel/.bash_logout ~
cp -f /etc/skel/.bash_profile ~
cp -f /etc/skel/.bashrc ~
cp -f /etc/skel/.gtkrc-2.0 ~
cp -f /etc/skel/.xinitrc ~

#Default theme
first-login-theme &>/dev/null

#Compositing mode - based on biglinux-themes
MODE="$(<$HOME/.big_performance)"
if [ "$MODE" = "0" ];then
    # Animation 0
    kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key AnimationSpeed 3
    kwriteconfig5 --file ~/.config/kdeglobals --group KDE --key AnimationDurationFactor ""
    kwriteconfig5 --file ~/.config/klaunchrc --group BusyCursorSettings --key Blinking false
    kwriteconfig5 --file ~/.config/klaunchrc --group BusyCursorSettings --key Bouncing true

    # Composition on
    kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key Enabled true

    # Opengl 2
    kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key GLCore false
    kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key Backend OpenGL

else
    # Animation 2
    kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key AnimationSpeed 1
    kwriteconfig5 --file ~/.config/kdeglobals --group KDE --key AnimationDurationFactor 0.5
    kwriteconfig5 --file ~/.config/klaunchrc --group BusyCursorSettings --key Blinking true
    kwriteconfig5 --file ~/.config/klaunchrc --group BusyCursorSettings --key Bouncing false

    # Composition on
    kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key Enabled true

    # Opengl 2
    kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key GLCore false
    kwriteconfig5 --file ~/.config/kwinrc --group Compositing --key Backend OpenGL
fi

sleep 1
echo -n "#"

exit
