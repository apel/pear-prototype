FROM gitlab-registry.cern.ch/linuxsupport/alma9-base@sha256:3298e9924ce26734aced8ffa054dc7a81f0ac5b48ad4979a888e70de358ff144
LABEL org.opencontainers.image.base.created="2026-06-03"

# Install SSM dependecies
RUN dnf install -y \
	epel-release \
	openssl-devel \
	wget && \
# Install SSM Python dependencies
	dnf install -y \
    python3-pip \
	python3-pyOpenSSL \
	python3-stomppy \
	python3-dirq \
	python3-cryptography \
    python3-daemon \
    python3-requests && \
# Install argo-ams-library
    cd /tmp && \
    wget http://rpm-repo.argo.grnet.gr/ARGO/prod/rocky9/python3-argo-ams-library-1.0.0-1.el9.noarch.rpm && \
    dnf install -y python3-argo-ams-library-1.0.0-1.el9.noarch.rpm && \
    rm python3-argo-ams-library-1.0.0-1.el9.noarch.rpm && \
# Install SSM
    wget https://github.com/apel/ssm/releases/download/4.0.0-1/apel-ssm-4.0.0-1.el9.noarch.rpm && \
    dnf install -y apel-ssm-4.0.0-1.el9.noarch.rpm && \
    rm apel-ssm-4.0.0-1.el9.noarch.rpm && \
# Install CA certificates
    cd /etc/yum.repos.d/ && \
    wget http://repository.egi.eu/sw/production/cas/1/current/repo-files/egi-trustanchors.repo && \
    dnf install -y ca-policy-egi-core && \
    rm egi-trustanchors.repo && \
# Clean up
    dnf autoremove -y && \
    dnf clean all && \
    rm -rf /var/cache/dnf

# Install necessary utilities
RUN dnf install -y gettext

COPY ./receiver.template.cfg /etc/apel/receiver.template.cfg
COPY ./dn_allowlist /etc/apel/dns

WORKDIR /app
COPY ./run.sh ./

RUN groupadd -g 1000 apeluser && \
    useradd -u 1000 -g apeluser apeluser
RUN chown -R apeluser:apeluser \
    /var/spool/apel \
    /var/log/apel \
    /var/run/apel \
    /etc/apel \
    /home/apeluser \
    /app
USER apeluser
