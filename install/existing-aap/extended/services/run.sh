#!/bin/bash
podman run --name aac-webserver --rm -p 8080:8080 \
  -v "${HOME}/reports:/srv/reports:ro,Z" \
  aac-reports-viewer:latest
