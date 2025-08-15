FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    DEBIAN_PRIORITY=high \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Base packages matching Streamlit image (UI + build deps)
RUN apt-get update && \
    apt-get -y upgrade && \
    apt-get -y install \
    xvfb \
    xterm \
    xdotool \
    scrot \
    imagemagick \
    sudo \
    mutter \
    x11vnc \
    build-essential \
    libssl-dev  \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libsqlite3-dev \
    curl \
    git \
    libncursesw5-dev \
    xz-utils \
    tk-dev \
    libxml2-dev \
    libxmlsec1-dev \
    libffi-dev \
    liblzma-dev \
    net-tools \
    netcat \
    software-properties-common && \
    add-apt-repository -y ppa:mozillateam/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    firefox-esr \
    x11-apps \
    xpdf \
    gedit \
    xpaint \
    tint2 \
    galculator \
    pcmanfm \
    unzip && \
    apt-get clean

# Install noVNC same as Streamlit image
RUN git clone --branch v1.5.0 https://github.com/novnc/noVNC.git /opt/noVNC && \
    git clone --branch v0.12.0 https://github.com/novnc/websockify /opt/noVNC/utils/websockify && \
    ln -s /opt/noVNC/vnc.html /opt/noVNC/index.html

# Create unprivileged user like Streamlit image
ENV USERNAME=computeruse
ENV HOME=/home/$USERNAME
RUN useradd -m -s /bin/bash -d $HOME $USERNAME && \
    echo "$USERNAME ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
USER computeruse
WORKDIR $HOME

# Install Python with pyenv (3.11.6)
RUN git clone https://github.com/pyenv/pyenv.git ~/.pyenv && \
    cd ~/.pyenv && src/configure && make -C src && cd .. && \
    echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc && \
    echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc && \
    echo 'eval "$(pyenv init -)"' >> ~/.bashrc
ENV PYENV_ROOT="$HOME/.pyenv"
ENV PATH="$PYENV_ROOT/bin:$PATH"
ENV PYENV_VERSION_MAJOR=3
ENV PYENV_VERSION_MINOR=11
ENV PYENV_VERSION_PATCH=6
ENV PYENV_VERSION=$PYENV_VERSION_MAJOR.$PYENV_VERSION_MINOR.$PYENV_VERSION_PATCH
RUN bash -lc 'eval "$(pyenv init -)" && pyenv install $PYENV_VERSION && pyenv global $PYENV_VERSION && pyenv rehash'
ENV PATH="$HOME/.pyenv/shims:$HOME/.pyenv/bin:$PATH"

# Upgrade pip and install backend requirements
RUN python -m pip install --upgrade pip==23.1.2 setuptools==58.0.4 wheel==0.40.0 && \
    python -m pip config set global.disable-pip-version-check true

# Copy and install backend requirements
COPY --chown=$USERNAME:$USERNAME legent-ai/requirements.txt $HOME/legent-ai/requirements.txt
RUN python -m pip install -r $HOME/legent-ai/requirements.txt

# Copy backend code and startup scripts
COPY --chown=$USERNAME:$USERNAME legent-ai/ /app/legent-ai/
COPY --chown=$USERNAME:$USERNAME legent-ai/image/ $HOME/
RUN chmod +x $HOME/*.sh

# Copy GUI configs from the Streamlit demo (tint2, launchers)
COPY --chown=$USERNAME:$USERNAME legent-ai/image/.config $HOME/.config

# Default GUI env
ENV DISPLAY_NUM=1 \
    DISPLAY=":1" \
    WIDTH=1280 \
    HEIGHT=800

EXPOSE 8000 6080

ENTRYPOINT ["./entrypoint.sh"]
