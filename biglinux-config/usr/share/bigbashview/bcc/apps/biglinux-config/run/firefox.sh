#!/usr/bin/env bash

PROG=$(pidof firefox)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

if [ "$1" = "skel" ];then
    rm -r ~/.mozilla
    cp -r /etc/skel/.mozilla ~/.mozilla
    echo -n "#"
else
    rm -r ~/.mozilla
    echo -n "#"
fi

exit
