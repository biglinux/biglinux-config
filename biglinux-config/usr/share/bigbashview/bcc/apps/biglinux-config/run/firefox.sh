#!/usr/bin/env bash

PROG=$(pidof firefox)

if [ -n "$PROG" ];then
    echo -n "$PROG"
    exit
fi

rm -r ~/.mozilla
echo -n "#"

exit
