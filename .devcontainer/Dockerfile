# Use the same base image as your devcontainer.json
FROM ubuntu:jammy

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000

# Install sudo and other utilities needed for user creation
RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create group and user with specified UID/GID, create home dir
RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m -s /bin/bash ${USERNAME} \
    && echo "${USERNAME} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME}

RUN echo "vscode ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Set default user (container will start as this user unless overridden)
USER ${USERNAME}
ENV HOME=/home/${USERNAME}
WORKDIR /home/${USERNAME}