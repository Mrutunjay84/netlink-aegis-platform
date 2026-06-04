#!/usr/bin/env bash

DJANGO_DIR=../../backend
NETLINK_SETTINGS=netlink_core.settings

python $DJANGO_DIR/manage.py $@ --settings=$NETLINK_SETTINGS
