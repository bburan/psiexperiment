from atom.api import Atom, Bool, Enum, List, Unicode, Typed


class PluginDescription(Atom):

    name = Unicode()
    title = Unicode()
    required = Bool()
    selected = Bool()
    manifest = Unicode()


class ParadigmDescription(Atom):

    name = Unicode()
    title = Unicode()
    plugins = List()
    type = Enum('ear', 'animal', 'cohort', 'calibration')

    def enable_plugin(self, plugin_name):
        for plugin in self.plugins:
            if plugin.name == plugin_name:
                plugin.selected = True
                return
        valid_plugins = ', '.join(p.name for p in self.plugins)
        raise ValueError(f'Plugin {plugin_name} does not exist. ' \
                         f'Valid options are {valid_plugins}')


class ExperimentDescription(Atom):

    name = Unicode()
    title = Unicode()
    io_manifest = Unicode()
    paradigm = Typed(ParadigmDescription)


abr_controller = PluginDescription(
    name='controller',
    title='Controller',
    required=True,
    manifest='psi.application.experiment.abr_base.ControllerManifest',
)


speaker_calibration_controller = PluginDescription(
    name='controller',
    title='Controller',
    required=True,
    manifest='psi.application.experiment.speaker_calibration.ControllerManifest',
)


temperature_mixin = PluginDescription(
    name='temperature',
    title='Temperature display',
    required=False,
    selected=False,
    manifest='psi.application.experiment.cfts_mixins.TemperatureMixinManifest',
)


eeg_view_mixin = PluginDescription(
    name='eeg_view',
    title='EEG display',
    required=False,
    selected=False,
    manifest='psi.application.experiment.cfts_mixins.EEGViewMixinManifest',
)


in_ear_calibration_mixin = PluginDescription(
    name='in_ear_calibration',
    title='In-ear calibration',
    required=False,
    selected=True,
    manifest='psi.application.experiment.cfts_mixins.InEarCalibrationMixinManifest',
)


abr_experiment = ParadigmDescription(
    name='abr',
    title='ABR',
    type='ear',
    plugins=[
        abr_controller,
        temperature_mixin,
        eeg_view_mixin,
        in_ear_calibration_mixin,
    ]
)


speaker_calibration_experiment = ParadigmDescription(
    name='speaker_calibration',
    title='Speaker calibration',
    type='ear',
    plugins=[
        speaker_calibration_controller,
    ]
)


noise_exposure_controller = PluginDescription(
    name='noise_exposure_controller',
    title='Noise exposure controller',
    required=True,
    selected=True,
    manifest='psi.application.experiment.noise_exposure.ControllerManifest',
)


noise_exposure_experiment = ParadigmDescription(
    name='noise_exposure',
    title='Noise exposure',
    type='cohort',
    plugins=[
        noise_exposure_controller,
    ],
)


appetitive_gonogo_controller = PluginDescription(
    name='appetitive_gonogo_controller',
    title='Appetitive GO-NOGO controller',
    required=True,
    selected=True,
    manifest='psi.application.experiment.appetitive.ControllerManifest',
)


appetitive_experiment = ParadigmDescription(
    name='appetitive_gonogo_food',
    title='Appetitive GO-NOGO food',
    type='animal',
    plugins=[
        appetitive_gonogo_controller,
    ],
)


pistonphone_controller = PluginDescription(
    name='pistonphone_controller',
    title='Pistonphone controller',
    required=True,
    selected=True,
    manifest='psi.application.experiment.pistonphone_calibration.ControllerManifest',
)


pistonphone_calibration = ParadigmDescription(
    name='pistonphone_calibration',
    title='Pistonphone calibration',
    type='calibration',
    plugins=[
        pistonphone_controller
    ],
)


golay_controller = PluginDescription(
    name='golay_controller',
    title='Golay controller',
    required=True,
    selected=True,
    manifest='psi.application.experiment.pt_calibration.GolayControllerManifest',
)


chirp_controller = PluginDescription(
    name='chirp_controller',
    title='Chirp controller',
    required=True,
    selected=True,
    manifest='psi.application.experiment.pt_calibration.ChirpControllerManifest',
)


pt_calibration_chirp = ParadigmDescription(
    name='pt_calibration_chirp',
    title='Probe tube calibration (chirp)',
    type='calibration',
    plugins=[
        chirp_controller,
    ],
)


pt_calibration_golay = ParadigmDescription(
    name='pt_calibration_golay',
    title='Probe tube calibration (golay)',
    type='calibration',
    plugins=[
        golay_controller,
    ],
)


experiments = {
    'abr': abr_experiment,
    'speaker_calibration': speaker_calibration_experiment,
    'appetitive_gonogo_food': appetitive_experiment,
    'noise_exposure': noise_exposure_experiment,
    'pistonphone_calibration': pistonphone_calibration,
    'pt_calibration_golay': pt_calibration_golay,
    'pt_calibration_chirp': pt_calibration_chirp,
}


def get_experiments(type):
    return [e for e in experiments.values() if e.type == type]
