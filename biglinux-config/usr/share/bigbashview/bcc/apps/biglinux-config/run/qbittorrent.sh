#!/usr/bin/env bash

PROG=$(pidof qbittorrent)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ];then
    rm -r ~/.config/qBittorrent
    rm -r ~/.local/share/data/qBittorrent
    cp -r /etc/skel/.config/qBittorrent ~/.config/qBittorrent
    cp -r /etc/skel/.local/share/data/qBittorrent ~/.local/share/data/qBittorrent
    echo -n "#"
else
    rm -r ~/.config/qBittorrent
    rm -r ~/.local/share/data/qBittorrent
    echo -n "#"
fi

exit
