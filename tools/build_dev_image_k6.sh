#!/bin/sh
docker build -f tools/dev_image_k6/Dockerfile -t mlabproject/kicad_auto . --no-cache
