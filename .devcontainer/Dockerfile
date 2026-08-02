FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# The base image currently carries an unrelated Yarn repository with a rotated/missing signing key.
# Removing that source keeps apt fail-closed and allows official Dev Container features to install.
RUN rm -f /etc/apt/sources.list.d/yarn.list /etc/apt/sources.list.d/yarn.sources
