FROM ghcr.io/inti-cmnb/kicad10_auto_full:latest
LABEL AUTHOR Salvador E. Tropea <stropea@inti.gob.ar>
LABEL Description="Export various files from KiCad projects (KiCad 10)"

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Patch: support cubic bezier (C) in Edge.Cuts board outline (gr_curve).
# KiCad exports gr_curve as SVG paths with C directly adjacent to coordinates
# (e.g. 'C144.0000'), which the original SvgPathItem parser does not handle.
# Remove this COPY once the fix is merged upstream and included in the base image.
COPY kibot/PcbDraw/plot.py /tmp/kibot_plot_patch.py
RUN python3 -c "\
import kibot.PcbDraw.plot, shutil, os; \
shutil.copy('/tmp/kibot_plot_patch.py', os.path.abspath(kibot.PcbDraw.plot.__file__))"

WORKDIR /mnt

ENTRYPOINT [ "/entrypoint.sh" ]
