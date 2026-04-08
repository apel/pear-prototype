#!/bin/bash

envsubst < /etc/apel/receiver.template.cfg > /etc/apel/receiver.cfg

ssmreceive
