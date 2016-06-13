import logging
log = logging.getLogger(__name__)

from functools import partial

import numpy as np

from atom.api import Enum, Bool, Typed, Property
from enaml.workbench.plugin import Plugin

from .api import Channel, Engine, Output, ExperimentAction

from ..token import get_token_manifest


IO_POINT = 'psi.controller.io'
OUTPUT_POINT = 'psi.controller.outputs'
ENGINE_POINT = 'psi.controller.engines'
ACTION_POINT = 'psi.controller.actions'


class BaseController(Plugin):

    # Tracks the state of the controller.
    experiment_state = Enum('initialized', 'running', 'paused', 'stopped')
    running = Property()

    # Provides direct access to plugins rather than going through the core
    # command system. Right now the context plugin is so fundamentally important
    # to the controller that it would be cumbersome to use the core command
    # system.
    core = Typed(Plugin)
    context = Typed(Plugin)
    data = Typed(Plugin)

    # We should not respond to changes during the course of a trial. These flags
    # indicate changes or requests from the user are pending and should be
    # processed when the opportunity arises (e.g., at the end of the trial).
    _apply_requested = Bool(False)
    _remind_requested = Bool(False)
    _pause_requested = Bool(False)

    _engines = Typed(dict, {})
    _io = Typed(dict, {})
    _outputs = Typed(dict, {})
    _channels = Typed(dict, {})
    _channel_outputs = Typed(dict, {})
    _master_engine = Typed(Engine)

    # TODO: Define action groups to minimize errors.
    _actions = Typed(dict, {})

    def start(self):
        self.core = self.workbench.get_plugin('enaml.workbench.core')
        self.context = self.workbench.get_plugin('psi.context')
        self.data = self.workbench.get_plugin('psi.data')
        self._refresh_engines()
        self._refresh_io()
        self._refresh_actions()
        self._bind_observers()

    def stop(self):
        self._unbind_observers()

    def _bind_observers(self):
        self.workbench.get_extension_point(IO_POINT) \
            .observe('extensions', self._refresh_io)
        self.workbench.get_extension_point(ENGINE_POINT) \
            .observe('extensions', self._refresh_engines)

    def _unbind_observers(self):
        self.workbench.get_extension_point(IO_POINT) \
            .unobserve('extensions', self._refresh_io)
        self.workbench.get_extension_point(ENGINE_POINT) \
            .unobserve('extensions', self._refresh_engines)

    def _refresh_io(self):
        point = self.workbench.get_extension_point(IO_POINT)
        io = {}
        outputs = {}
        channels = {}
        channel_outputs = {}

        for extension in point.extensions:
            for channel in extension.get_children(Channel):
                engine = self._engines[channel.engine_name]
                channel.engine = engine

                engine_io = io.setdefault(channel.engine_name, {})
                engine_io.setdefault(channel.io_type, []).append(channel)
                channels[channel.name] = channel

        for extension in point.extensions:
            for output in extension.get_children(Output):
                channel = channels[output.channel_name]
                output.channel = channel
                outputs[output.name] = output

                co = channel_outputs.setdefault(output.mode, {})
                if output.channel in co:
                    m = '{} output already defined for {}' \
                        .format(output.mode, output.channel)
                    raise ValueError(m)
                co[output.channel_name] = output

        # TODO: We have four different ways of organizing the information loaded
        # under this extension point. Is there a simpler, more logical way to
        # organize everything?
        self._io = io
        self._outputs = outputs
        self._channels = channels
        self._channel_outputs = channel_outputs

    def _refresh_engines(self):
        engines = {}
        master_engine = None
        point = self.workbench.get_extension_point(ENGINE_POINT)
        for extension in point.extensions:
            for engine in extension.get_children(Engine):
                engines[engine.name] = engine
                if engine.master_clock:
                    if master_engine is not None:
                        m = 'Only one engine can be defined as the master'
                        raise ValueError(m)
                    master_engine = engine
        self._master_engine = master_engine
        self._engines = engines

    def _refresh_actions(self):
        actions = {}
        point = self.workbench.get_extension_point(ACTION_POINT)
        for extension in point.extensions:
            for action in extension.get_children(ExperimentAction):
                subgroup = actions.setdefault(action.event, [])
                subgroup.append(action)
        self._actions = actions

    def start_engines(self):
        for name, config in self._io.items():
            log.debug('Configuring engine {}'.format(name))
            engine = self._engines[name]
            engine.configure(config)
            engine.register_ao_callback(partial(self.ao_callback, name))
            engine.register_ai_callback(partial(self.ai_callback, name))
            engine.register_et_callback(partial(self.et_callback, name))
            engine.register_di_callback(partial(self.di_callback, name))
            engine.register_di_change_callback(partial(self.et_callback, name))

        for output in self._outputs.values():
            # TODO: Sort of a minor hack. We can clean this up eventually.
            output._plugin.initialize(output.channel.fs)

        for engine in self._engines.values():
            engine.start()

    def stop_engines(self):
        for engine in self._engines.values():
            engine.stop()

    def configure_output(self, output_name, token_name):
        output = self._outputs[output_name]
        if output._token_name == token_name:
            return
        if output._plugin:
            self.workbench.unregister(output._plugin_id)
        manifest_description = get_token_manifest(token_name)
        scope = 'experiment' if output.mode == 'continuous' else 'trial'
        manifest = manifest_description(output.name, scope=scope,
                                        label_base=output.label)
        self.workbench.register(manifest)
        output._plugin_id = manifest.id
        output._plugin = self.workbench.get_plugin(manifest.id)
        output._token_name = token_name

    def invoke_actions(self, event):
        log.debug('Invoking actions for {}'.format(event))
        for action in self._actions[event]:
            log.debug('Invoking command {}'.format(action.command))
            self.core.invoke_command(action.command)

    def request_apply(self):
        if not self.apply_changes():
            log.debug('Apply requested')
            self._apply_requested = True

    def request_remind(self):
        self._remind_requested = True

    def request_pause(self):
        if not self.pause_experiment():
            log.debug('Pause requested')
            self._pause_requested = True

    def request_resume(self):
        self._pause_requested = False
        self.experiment_state = 'running'

    def apply_changes(self):
        raise NotImplementedError

    def start_experiment(self):
        raise NotImplementedError

    def stop_experiment(self):
        raise NotImplementedError

    def pause_experiment(self):
        raise NotImplementedError

    def start_trial(self):
        raise NotImplementedError

    def end_trial(self):
        raise NotImplementedError

    def ao_callback(self, engine, data):
        raise NotImplementedError

    def ai_callback(self, engine, data):
        raise NotImplementedError

    def et_callback(self, engine, line, edge, timestamp):
        raise NotImplementedError

    def get_ts(self):
        return self._master_engine.get_ts()
