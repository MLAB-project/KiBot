# -*- coding: utf-8 -*-
# Copyright (c) 2020-2022 Salvador E. Tropea
# Copyright (c) 2020-2022 Instituto Nacional de Tecnología Industrial
# Copyright (c) 2018 John Beard
# License: GPL-3.0
# Project: KiBot (formerly KiPlot)
# Adapted from: https://github.com/johnbeard/kiplot
"""
Main KiBot code
"""

import os
import re
from sys import exit
from sys import path as sys_path
from shutil import which
from subprocess import run, PIPE
from glob import glob
from distutils.version import StrictVersion
from importlib.util import (spec_from_file_location, module_from_spec)
from collections import OrderedDict

from .gs import GS
from .registrable import RegOutput
from .misc import (PLOT_ERROR, MISSING_TOOL, CMD_EESCHEMA_DO, URL_EESCHEMA_DO, CORRUPTED_PCB,
                   EXIT_BAD_ARGS, CORRUPTED_SCH, EXIT_BAD_CONFIG, WRONG_INSTALL, UI_SMD, UI_VIRTUAL,
                   MOD_SMD, MOD_THROUGH_HOLE, MOD_VIRTUAL, W_PCBNOSCH, W_NONEEDSKIP, W_WRONGCHAR, name2make, W_TIMEOUT,
                   W_KIAUTO)
from .error import PlotError, KiPlotConfigurationError, config_error, trace_dump
from .pre_base import BasePreFlight
from .kicad.v5_sch import Schematic, SchFileError, SchError
from .kicad.v6_sch import SchematicV6
from .kicad.config import KiConfError
from . import log

logger = log.get_logger()
# Cache to avoid running external many times to check their versions
script_versions = {}
actions_loaded = False


def _import(name, path):
    # Python 3.4+ import mechanism
    spec = spec_from_file_location("kibot."+name, path)
    mod = module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except ImportError as e:
        trace_dump()
        logger.error('Unable to import plug-ins: '+str(e))
        logger.error('Make sure you used `--no-compile` if you used pip for installation')
        logger.error('Python path: '+str(sys_path))
        exit(WRONG_INSTALL)


def _load_actions(path, load_internals=False):
    logger.debug("Importing from "+path)
    lst = glob(os.path.join(path, 'out_*.py')) + glob(os.path.join(path, 'pre_*.py'))
    lst += glob(os.path.join(path, 'var_*.py')) + glob(os.path.join(path, 'fil_*.py'))
    if load_internals:
        lst += [os.path.join(path, 'globals.py')]
    for p in lst:
        name = os.path.splitext(os.path.basename(p))[0]
        logger.debug("- Importing "+name)
        _import(name, p)


def load_actions():
    """ Load all the available outputs and preflights """
    global actions_loaded
    if actions_loaded:
        return
    actions_loaded = True
    from kibot.mcpyrate import activate
    # activate.activate()
    _load_actions(os.path.abspath(os.path.dirname(__file__)), True)
    home = os.environ.get('HOME')
    if home:
        dir = os.path.join(home, '.config', 'kiplot', 'plugins')
        if os.path.isdir(dir):
            _load_actions(dir)
        dir = os.path.join(home, '.config', 'kibot', 'plugins')
        if os.path.isdir(dir):
            _load_actions(dir)
    # de_activate in old mcpy
    if 'deactivate' in activate.__dict__:
        logger.debug('Deactivating macros')
        activate.deactivate()


def check_version(command, version):
    global script_versions
    if command in script_versions:
        return
    cmd = [command, '--version']
    logger.debug('Running: '+str(cmd))
    result = run(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True)
    z = re.match(command + r' (\d+\.\d+\.\d+)', result.stdout, re.IGNORECASE)
    if not z:
        z = re.search(r'Version: (\d+\.\d+\.\d+)', result.stdout, re.IGNORECASE)
    if not z:
        logger.error('Unable to determine ' + command + ' version:\n' +
                     result.stdout)
        exit(MISSING_TOOL)
    res = z.groups()
    if StrictVersion(res[0]) < StrictVersion(version):
        logger.error('Wrong version for `'+command+'` ('+res[0]+'), must be ' +
                     version+' or newer.')
        exit(MISSING_TOOL)
    script_versions[command] = res[0]


def check_script(cmd, url, version=None):
    if which(cmd) is None:
        logger.error('No `'+cmd+'` command found.\n'
                     'Please install it, visit: '+url)
        exit(MISSING_TOOL)
    if version is not None:
        check_version(cmd, version)


def check_eeschema_do():
    check_script(CMD_EESCHEMA_DO, URL_EESCHEMA_DO, '1.5.4')


def search_as_plugin(cmd, names):
    """ If a command isn't in the path look for it in the KiCad plugins """
    if which(cmd) is not None:
        return cmd
    for dir in GS.kicad_plugins_dirs:
        for name in names:
            fname = os.path.join(dir, name, cmd)
            if os.path.isfile(fname):
                logger.debug('Using `{}` for `{}` ({})'.format(fname, cmd, name))
                return fname
    return cmd


def extract_errors(text):
    in_error = in_warning = False
    msg = ''
    for line in text.split('\n'):
        line += '\n'
        if line[0] == ' ' and (in_error or in_warning):
            msg += line
        else:
            if in_error:
                in_error = False
                logger.error(msg.rstrip())
            elif in_warning:
                in_warning = False
                logger.warning(W_KIAUTO+msg.rstrip())
        if line.startswith('ERROR:'):
            in_error = True
            msg = line[6:]
        elif line.startswith('WARNING:'):
            in_warning = True
            msg = line[8:]
    if in_error:
        in_error = False
        logger.error(msg.rstrip())
    elif in_warning:
        in_warning = False
        logger.warning(W_KIAUTO+msg.rstrip())


def exec_with_retry(cmd):
    logger.debug('Executing: '+str(cmd))
    if GS.debug_level > 2:
        logger.debug('Command line: '+' '.join(cmd))
    retry = 2
    while retry:
        result = run(cmd, stdout=PIPE, stderr=PIPE, universal_newlines=True)
        ret = result.returncode
        retry -= 1
        if ret > 0 and ret < 128 and retry:
            logger.debug('Failed with error {}, retrying ...'.format(ret))
        else:
            extract_errors(result.stderr)
            err = '> '+result.stderr.replace('\n', '\n> ')
            logger.debug('Output from command:\n'+err)
            if 'Timed out' in err:
                logger.warning(W_TIMEOUT+'Time out detected, on slow machines or complex projects try:')
                logger.warning(W_TIMEOUT+'`kiauto_time_out_scale` and/or `kiauto_wait_start` global options')
            return ret


def add_extra_options(cmd):
    is_gitlab_ci = 'GITLAB_CI' in os.environ
    video_remove = (not GS.debug_enabled) and is_gitlab_ci
    if GS.debug_enabled:
        cmd.insert(1, '-'+'v'*GS.debug_level)
    if GS.debug_enabled or is_gitlab_ci:
        # Forcing record on GitLab CI/CD (black magic)
        cmd.insert(1, '-r')
    if GS.global_kiauto_time_out_scale:
        cmd.insert(1, str(GS.global_kiauto_time_out_scale))
        cmd.insert(1, '--time_out_scale')
    if GS.global_kiauto_wait_start:
        cmd.insert(1, str(GS.global_kiauto_wait_start))
        cmd.insert(1, '--wait_start')
    return cmd, video_remove


def load_board(pcb_file=None):
    if GS.board is not None:
        # Already loaded
        return GS.board
    import pcbnew
    if not pcb_file:
        GS.check_pcb()
        pcb_file = GS.pcb_file
    try:
        board = pcbnew.LoadBoard(pcb_file)
        if BasePreFlight.get_option('check_zone_fills'):
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        if GS.global_units and GS.ki6():
            # In KiCad 6 "dimensions" has units.
            # The default value is DIM_UNITS_MODE_AUTOMATIC.
            # But this has a meaning only in the GUI where you have default units.
            # So now we have global.units and here we patch the board.
            UNIT_NAME_TO_INDEX = {'millimeters': pcbnew.DIM_UNITS_MODE_MILLIMETRES,
                                  'inches': pcbnew.DIM_UNITS_MODE_INCHES,
                                  'mils': pcbnew.DIM_UNITS_MODE_MILS}
            forced_units = UNIT_NAME_TO_INDEX[GS.global_units]
            for dr in board.GetDrawings():
                if dr.GetClass().startswith('PCB_DIM_') and dr.GetUnitsMode() == pcbnew.DIM_UNITS_MODE_AUTOMATIC:
                    dr.SetUnitsMode(forced_units)
                    dr.Update()
        GS.board = board
    except OSError as e:
        logger.error('Error loading PCB file. Corrupted?')
        logger.error(e)
        exit(CORRUPTED_PCB)
    assert board is not None
    logger.debug("Board loaded")
    return board


def load_any_sch(file, project):
    logger.debug("Loading Schematic file: "+file)
    if file[-9:] == 'kicad_sch':
        sch = SchematicV6()
        load_libs = False
    else:
        sch = Schematic()
        load_libs = True
    logger.debug(repr(sch))
    logger.debug(repr(load_libs))
    try:
        sch.load(file, project)
        if load_libs:
            sch.load_libs(file)
        if GS.debug_level > 1:
            logger.debug('Schematic dependencies: '+str(sch.get_files()))
    except SchFileError as e:
        trace_dump()
        logger.error('At line {} of `{}`: {}'.format(e.line, e.file, e.msg))
        logger.error('Line content: `{}`'.format(e.code))
        exit(CORRUPTED_SCH)
    except SchError as e:
        trace_dump()
        logger.error('While loading `{}`'.format(file))
        logger.error(str(e))
        exit(CORRUPTED_SCH)
    except KiConfError as e:
        trace_dump()
        logger.error('At line {} of `{}`: {}'.format(e.line, e.file, e.msg))
        logger.error('Line content: `{}`'.format(e.code))
        exit(EXIT_BAD_CONFIG)
    return sch


def load_sch():
    if GS.sch:  # Already loaded
        return
    GS.check_sch()
    GS.sch = load_any_sch(GS.sch_file, GS.sch_basename)


def get_board_comps_data(comps):
    """ Add information from the PCB to the list of components from the schematic.
        Note that we do it every time the function is called to reset transformation filters like rot_footprint. """
    if not GS.pcb_file:
        return
    load_board()
    comps_hash = {c.ref: c for c in comps}
    for m in GS.get_modules():
        ref = m.GetReference()
        if ref not in comps_hash:
            logger.warning(W_PCBNOSCH + '`{}` component in board, but not in schematic'.format(ref))
            continue
        c = comps_hash[ref]
        c.bottom = m.IsFlipped()
        c.footprint_rot = m.GetOrientationDegrees()
        center = GS.get_center(m)
        c.footprint_x = center.x
        c.footprint_y = center.y
        (c.footprint_w, c.footprint_h) = GS.get_fp_size(m)
        attrs = m.GetAttributes()
        if GS.ki5():
            # KiCad 5
            if attrs == UI_SMD:
                c.smd = True
            elif attrs == UI_VIRTUAL:
                c.virtual = True
            else:
                c.tht = True
        else:
            # KiCad 6
            if attrs & MOD_SMD:
                c.smd = True
            if attrs & MOD_THROUGH_HOLE:
                c.tht = True
            if attrs & MOD_VIRTUAL == MOD_VIRTUAL:
                c.virtual = True


def preflight_checks(skip_pre):
    logger.debug("Preflight checks")

    if skip_pre is not None:
        if skip_pre == 'all':
            logger.debug("Skipping all preflight actions")
            return
        else:
            skip_list = skip_pre.split(',')
            for skip in skip_list:
                if skip == 'all':
                    logger.error('All can\'t be part of a list of actions '
                                 'to skip. Use `--skip all`')
                    exit(EXIT_BAD_ARGS)
                else:
                    if not BasePreFlight.is_registered(skip):
                        logger.error('Unknown preflight `{}`'.format(skip))
                        exit(EXIT_BAD_ARGS)
                    o_pre = BasePreFlight.get_preflight(skip)
                    if not o_pre:
                        logger.warning(W_NONEEDSKIP + '`{}` preflight is not in use, no need to skip'.format(skip))
                    else:
                        logger.debug('Skipping `{}`'.format(skip))
                        o_pre.disable()
    BasePreFlight.run_enabled()


def get_output_dir(o_dir, obj, dry=False):
    # outdir is a combination of the config and output
    outdir = os.path.abspath(obj.expand_dirname(os.path.join(GS.out_dir, o_dir)))
    # Create directory if needed
    logger.debug("Output destination: {}".format(outdir))
    if not dry and not os.path.exists(outdir):
        os.makedirs(outdir)
    return outdir


def config_output(out, dry=False):
    if out._configured:
        return
    # Should we load the PCB?
    if not dry:
        if out.is_pcb():
            load_board()
        if out.is_sch():
            load_sch()
    try:
        out.config(None)
    except KiPlotConfigurationError as e:
        config_error("In section '"+out.name+"' ("+out.type+"): "+str(e))


def run_output(out):
    if out._done:
        return
    GS.current_output = out.name
    try:
        out.run(get_output_dir(out.dir, out))
        out._done = True
    except PlotError as e:
        logger.error("In output `"+str(out)+"`: "+str(e))
        exit(PLOT_ERROR)
    except KiPlotConfigurationError as e:
        config_error("In section '"+out.name+"' ("+out.type+"): "+str(e))


def generate_outputs(outputs, target, invert, skip_pre, cli_order):
    logger.debug("Starting outputs for board {}".format(GS.pcb_file))
    preflight_checks(skip_pre)
    # Check if the preflights pulled options
    for out in RegOutput.get_prioritary_outputs():
        config_output(out)
        logger.info('- '+str(out))
        run_output(out)
    # Check if all must be skipped
    n = len(target)
    if n == 0 and invert:
        # Skip all targets
        logger.debug('Skipping all outputs')
        return
    # Check we got a valid list of outputs
    for name in target:
        out = RegOutput.get_output(name)
        if out is None:
            logger.error('Unknown output `{}`'.format(name))
            exit(EXIT_BAD_ARGS)
    # Generate outputs
    if cli_order and not invert:
        # Use the CLI order
        for name in target:
            out = RegOutput.get_output(name)
            config_output(out)
            logger.info('- '+str(out))
            run_output(out)
    else:
        # Use the declaration order
        for out in RegOutput.get_outputs():
            if (((n == 0 or ((out.name not in target) and invert)) and out.run_by_default) or
               ((out.name in target) and not invert)):
                config_output(out)
                logger.info('- '+str(out))
                run_output(out)
            else:
                logger.debug('Skipping `%s` output', str(out))


def adapt_file_name(name):
    if not name.startswith('/usr'):
        name = os.path.relpath(name)
    name = name.replace(' ', r'\ ')
    if '$' in name:
        logger.warning(W_WRONGCHAR+'Wrong character in file name `{}`'.format(name))
    return name


def gen_global_targets(f, pre_targets, out_targets, type):
    extra_targets = []
    pre = 'pre_'+type
    out = 'out_'+type
    all = 'all_'+type
    if pre_targets:
        f.write('{}:{}\n\n'.format(pre, pre_targets))
        extra_targets.append(pre)
    if out_targets:
        f.write('{}:{}\n\n'.format(out, out_targets))
        extra_targets.append(out)
    if pre_targets or out_targets:
        tg = ''
        if pre_targets:
            tg = ' '+pre
        if out_targets:
            tg += ' '+out
        f.write('{}:{}\n\n'.format(all, tg))
        extra_targets.append(all)
    return extra_targets


def get_pre_targets(targets, dependencies, is_pre):
    pcb_targets = sch_targets = ''
    prefs = BasePreFlight.get_in_use_objs()
    try:
        for pre in prefs:
            tg = pre.get_targets()
            if not tg:
                continue
            name = pre._name
            targets[name] = [adapt_file_name(fn) for fn in tg]
            dependencies[name] = [adapt_file_name(fn) for fn in pre.get_dependencies()]
            is_pre.add(name)
            if pre.is_sch():
                sch_targets += ' '+name
            if pre.is_pcb():
                pcb_targets += ' '+name
    except KiPlotConfigurationError as e:
        config_error("In preflight '"+name+"': "+str(e))
    return pcb_targets, sch_targets


def get_out_targets(outputs, ori_names, targets, dependencies, comments):
    pcb_targets = sch_targets = ''
    try:
        for out in outputs:
            name = name2make(out.name)
            ori_names[name] = out.name
            tg = out.get_targets(out.expand_dirname(os.path.join(GS.out_dir, out.dir)))
            if not tg:
                continue
            targets[name] = [adapt_file_name(fn) for fn in tg]
            dependencies[name] = [adapt_file_name(fn) for fn in out.get_dependencies()]
            if out.comment:
                comments[name] = out.comment
            if out.is_sch():
                sch_targets += ' '+name
            if out.is_pcb():
                pcb_targets += ' '+name
    except KiPlotConfigurationError as e:
        config_error("In output '"+name+"': "+str(e))
    return pcb_targets, sch_targets


def generate_makefile(makefile, cfg_file, outputs, kibot_sys=False):
    cfg_file = os.path.relpath(cfg_file)
    logger.info('- Creating makefile `{}` from `{}`'.format(makefile, cfg_file))
    with open(makefile, 'wt') as f:
        f.write('#!/usr/bin/make\n')
        f.write('# Automatically generated by KiBot from `{}`\n'.format(cfg_file))
        fname = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src', 'kibot'))
        if kibot_sys or not os.path.isfile(fname):
            fname = 'kibot'
        f.write('KIBOT?={}\n'.format(fname))
        dbg = ''
        if GS.debug_level > 0:
            dbg = '-'+'v'*GS.debug_level
        f.write('DEBUG?={}\n'.format(dbg))
        f.write('CONFIG={}\n'.format(cfg_file))
        if GS.sch_file:
            f.write('SCH={}\n'.format(os.path.relpath(GS.sch_file)))
        if GS.pcb_file:
            f.write('PCB={}\n'.format(os.path.relpath(GS.pcb_file)))
        f.write('DEST={}\n'.format(os.path.relpath(GS.out_dir)))
        f.write('KIBOT_CMD=$(KIBOT) $(DEBUG) -c $(CONFIG) -e $(SCH) -b $(PCB) -d $(DEST)\n')
        f.write('LOGFILE?=kibot_error.log\n')
        f.write('\n')
        # Configure all outputs
        for out in outputs:
            config_output(out)
        # Get all targets and dependencies
        targets = OrderedDict()
        dependencies = OrderedDict()
        comments = {}
        ori_names = {}
        is_pre = set()
        # Preflights
        pre_pcb_targets, pre_sch_targets = get_pre_targets(targets, dependencies, is_pre)
        # Outputs
        out_pcb_targets, out_sch_targets = get_out_targets(outputs, ori_names, targets, dependencies, comments)
        # all target
        f.write('#\n# Default target\n#\n')
        f.write('all: '+' '.join(targets.keys())+'\n\n')
        extra_targets = ['all']
        # PCB/SCH specific targets
        f.write('#\n# SCH/PCB targets\n#\n')
        extra_targets.extend(gen_global_targets(f, pre_sch_targets, out_sch_targets, 'sch'))
        extra_targets.extend(gen_global_targets(f, pre_pcb_targets, out_pcb_targets, 'pcb'))
        # Generate the output targets
        f.write('#\n# Available targets (outputs)\n#\n')
        for name, target in targets.items():
            f.write(name+': '+' '.join(target)+'\n\n')
        # Generate the output dependencies
        f.write('#\n# Rules and dependencies\n#\n')
        if GS.debug_enabled:
            kibot_cmd = '\t$(KIBOT_CMD)'
            log_action = ''
        else:
            kibot_cmd = '\t@$(KIBOT_CMD)'
            log_action = ' 2>> $(LOGFILE)'
        for name, dep in dependencies.items():
            if name in comments:
                f.write('# '+comments[name]+'\n')
            dep.append(cfg_file)
            f.write(' '.join(targets[name])+': '+' '.join(dep)+'\n')
            if name in is_pre:
                skip = filter(lambda n: n != name, is_pre)
                f.write('{} -s {} -i{}\n\n'.format(kibot_cmd, ','.join(skip), log_action))
            else:
                f.write('{} -s all "{}"{}\n\n'.format(kibot_cmd, ori_names[name], log_action))
        # Mark all outputs as PHONY
        f.write('.PHONY: '+' '.join(extra_targets+list(targets.keys()))+'\n')


# To avoid circular dependencies: Optionable needs it, but almost everything needs Optionable
GS.load_board = load_board
GS.load_sch = load_sch
