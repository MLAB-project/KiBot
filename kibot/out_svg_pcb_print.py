# -*- coding: utf-8 -*-
# Copyright (c) 2020-2022 Salvador E. Tropea
# Copyright (c) 2020-2022 Instituto Nacional de Tecnología Industrial
# License: GPL-3.0
# Project: KiBot (formerly KiPlot)
import os
import re
from .gs import GS
from .out_any_pcb_print import Any_PCB_PrintOptions
from .error import KiPlotConfigurationError
from .macros import macros, document, output_class  # noqa: F401
from .layer import Layer
from . import log

logger = log.get_logger()


class SVG_PCB_PrintOptions(Any_PCB_PrintOptions):
    def __init__(self):
        with document:
            self.output = GS.def_global_output
            """ Filename for the output SVG (%i=layers, %x=svg)"""
            self.enable_ki6_page_fix = True
            """ Enable workaround for KiCad 6 bug #11033 """
            self.enable_ki5_page_fix = True
            """ Enable workaround for KiCad 5 bug """
        super().__init__()
        self._expand_ext = 'svg'

    def run(self, output):
        super().run(output, svg=True)
        if (GS.ki6() and self.enable_ki6_page_fix) or (GS.ki5() and self.enable_ki5_page_fix):
            # KiCad 6.0.2 bug: https://gitlab.com/kicad/code/kicad/-/issues/11033
            o = self._parent
            out_files = o.get_targets(o.expand_dirname(os.path.join(GS.out_dir, o.dir)))
            for file in out_files:
                logger.debug('Patching SVG file `{}`'.format(file))
                with open(file, 'rt') as f:
                    text = f.read()
                text = re.sub(r'<svg (.*) width="(.*)" height="(.*)" viewBox="(\S+) (\S+) (\S+) (\S+)"',
                              r'<svg \1 width="\3" height="\2" viewBox="\4 \5 \7 \6"', text)
                text = re.sub(r'<rect x="(\S+)" y="(\S+)" width="(\S+)" height="(\S+)"',
                              r'<rect x="\1" y="\2" width="\4" height="\3"', text)
                with open(file, 'wt') as f:
                    f.write(text)


@output_class
class SVG_PCB_Print(BaseOutput):  # noqa: F821
    """ SVG PCB Print (Scalable Vector Graphics)
        Exports the PCB to the scalable vector graphics format.
        This output is what you get from the 'File/Print' menu in pcbnew. """
    def __init__(self):
        super().__init__()
        with document:
            self.options = SVG_PCB_PrintOptions
            """ [dict] Options for the `pdf_pcb_print` output """
            self.layers = Layer
            """ [list(dict)|list(string)|string] [all,selected,copper,technical,user]
                List of PCB layers to include in the PDF """

    def config(self, parent):
        super().config(parent)
        # We need layers
        if isinstance(self.layers, type):
            raise KiPlotConfigurationError("Missing `layers` list")
        self.options.set_layers(self.layers)
