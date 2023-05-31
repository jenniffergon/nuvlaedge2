ARG BASE_IMAGE=python:3.11.3-alpine3.18
ARG GO_BASE_IMAGE=golang:1.20.4-alpine3.18

# ------------------------------------------------------------------------
# Base builder stage containing the common python and alpine dependencies
# ------------------------------------------------------------------------
FROM ${BASE_IMAGE} AS base-builder
RUN apk update
RUN apk add gcc musl-dev linux-headers python3-dev

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

# ------------------------------------------------------------------------
# Bluetooth Peripheral builder
# ------------------------------------------------------------------------
FROM base-builder AS bt-builder
RUN apk add git g++ bluez-dev

WORKDIR /tmp/
RUN git clone https://github.com/pybluez/pybluez.git

WORKDIR /tmp/pybluez

# Pybluez has no maintenance altough it accepts contributions. Lock it to the current commit sha
RUN git checkout 4d46ce1

RUN python setup.py install


# ------------------------------------------------------------------------
FROM base-builder AS network-builder

COPY requirements.network.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt


# ------------------------------------------------------------------------
FROM base-builder AS modbus-builder

COPY requirements.modbus.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt


# ------------------------------------------------------------------------
FROM base-builder AS gpu-builder

COPY requirements.gpu.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt


# ------------------------------------------------------------------------
# System Manager builder
# ------------------------------------------------------------------------
FROM base-builder AS system-manager-builder
RUN apk add openssl-dev openssl libffi-dev
RUN apk add py3-cryptography="40.0.2-r1"

RUN cp -r /usr/lib/python3.11/site-packages/cryptography/ /usr/local/lib/python3.11/site-packages/
RUN cp -r /usr/lib/python3.11/site-packages/cryptography-40.0.2.dist-info/ /usr/local/lib/python3.11/site-packages/

COPY requirements.system-manager.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt


# ------------------------------------------------------------------------
# Agent builder
# ------------------------------------------------------------------------
FROM base-builder AS agent-builder

COPY requirements.agent.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt


# ------------------------------------------------------------------------
FROM base-builder AS nuvlaedge-builder

# Extract and separate requirements from package install to accelerate building process.
# Package dependency install is the Slow part of the building process
COPY --from=agent-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=system-manager-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=network-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=modbus-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=bt-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=gpu-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

COPY dist/nuvlaedge-*.whl /tmp/
RUN pip install /tmp/nuvlaedge-*.whl


FROM ${GO_BASE_IMAGE} AS golang-builder
# Build Golang usb peripehral
RUN apk update
RUN apk add libusb-dev udev pkgconfig gcc musl-dev

COPY nuvlaedge/peripherals/usb/ /opt/usb/
WORKDIR /opt/usb/

RUN go mod tidy && go build


FROM ${BASE_IMAGE}
COPY --from=golang-builder /opt/usb/nuvlaedge /usr/sbin/usb

# ------------------------------------------------------------------------
# Required alpine packages
# ------------------------------------------------------------------------
COPY --from=nuvlaedge-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=nuvlaedge-builder /usr/local/bin /usr/local/bin


# ------------------------------------------------------------------------
# Library required by py-cryptography (pyopenssl).
# By copying it from base builder we save up ~100MB of the gcc library
# ------------------------------------------------------------------------
COPY --from=nuvlaedge-builder /usr/lib/libgcc_s.so.1 /usr/lib/


# ------------------------------------------------------------------------
# GPU Peripheral setup
# ------------------------------------------------------------------------
RUN mkdir /opt/scripts/
COPY nuvlaedge/peripherals/gpu/cuda_scan.py /opt/nuvlaedge/scripts/gpu/
COPY nuvlaedge/peripherals/gpu/Dockerfile.gpu /etc/nuvlaedge/scripts/gpu/


# ------------------------------------------------------------------------
# REquired packages for the Agent
# ------------------------------------------------------------------------
RUN apk update
RUN apk add --no-cache procps curl mosquitto-clients lsblk openssl


# ------------------------------------------------------------------------
# Required packages for USB peripheral discovery
# ------------------------------------------------------------------------
RUN apk add --no-cache libusb-dev udev


# ------------------------------------------------------------------------
# Required for bluetooth discovery
# ------------------------------------------------------------------------
RUN apk add --no-cache bluez-dev

# ------------------------------------------------------------------------
# Setup Compute-API
# ------------------------------------------------------------------------
RUN apk add --no-cache socat

COPY scripts/compute-api/api.sh /usr/bin/api
RUN chmod +x /usr/bin/api


# ------------------------------------------------------------------------
# Setup VPN Client
# ------------------------------------------------------------------------
RUN apk add --no-cache openvpn

COPY scripts/vpn-client/* /opt/nuvlaedge/scripts/vpn-client/
RUN mv /opt/nuvlaedge/scripts/vpn-client/openvpn-client.sh /usr/bin/openvpn-client
RUN chmod +x /usr/bin/openvpn-client
RUN chmod +x /opt/nuvlaedge/scripts/vpn-client/get_ip.sh
RUN chmod +x /opt/nuvlaedge/scripts/vpn-client/wait-for-vpn-update.sh


# ------------------------------------------------------------------------
# Copy configuration files
# ------------------------------------------------------------------------
COPY nuvlaedge/agent/config/agent_logger_config.conf /etc/nuvlaedge/agent/config/agent_logger_config.conf


# ------------------------------------------------------------------------
# Set up Job engine
# ------------------------------------------------------------------------


VOLUME /etc/nuvlaedge/database

WORKDIR /opt/nuvlaedge/
