ψ<sub>experiment</sub>
======================

Psiexperiment is a plugin-based experiment controller that facilitates the
process of writing experiments. There are four core plugins: context,
experiment, controller and data.

Terminology
-----------

### Context

Every experiment has a set of variables that define the behavior. These
variables range from the stimulus frequency and level to the intertrial
interval duration. Sometimes these variables need to be expressed as functions
of other variables, or the value of the variable needs to vary in a random
fashion.

A *context item* provides information about a value that is managed by the
context plugin. When defining a context item in one of your plugin manifests,
you will provide basic information about the item (e.g., a GUI label, compact
GUI label and numpy dtype). This information will be used by plugins that
interact with the context plugin (for example, the name and dtype of the
context item will be used by the HDF5Store plugin to set up the table that
stores acquired trial data).

There are currently three specific types of context items. A *result* is a
value provided by a plugin. It cannot be defined by the user. Common use cases
may include the values computed after a trial is acquired (e.g., one can
compute the `reaction_time` and provide it as a result).

A *parameter* is a value that can be configured by the user before and during
an experiment. While the value of the parameter can be modified by the user
during the experiment, it cannot be roved. There are some parameters that do
not make sense as roving parameters. For example, if we define a
`go_probability` parameter that determines the probability that the next trial
is a GO trial instead of a NOGO, it does not make sense to rove this value from
trial-to-trial. It, however, may make sense to change this during the couse of
an experiemnt (e.g., during training).

A *roving parameter* is like a parameter, except that it can be roved from
trial to trial. When selected for roving, the next value of the parameter is
provided by a selector.

A *selector* maintains a sequence of expressions for one or more roving
parameters. In some experiments, you'll only have a single selector. In other
experiments, you may want multiple selectors (e.g., one for go trials, one for
remind trials and one for nogo trials). Right now, the only difference between
different types of selectors will be the GUI that's presented to the user for
configuring the sequence of values. Internally, all of them maintain a list of
values that should be presented on successive trials.

### Controller

The controller is the central plugin of the experiment system. It's responsible
for managing a series of *engines* and *experiment actions*. 

#### Engine

An *engine* communicates with a data acquisition device (e.g., a NI-DAQmx
card). Each engine manages a set of analog and digital *channels*. The channel
declaration contains sufficient information (e.g., expected range of values,
sampling frequency, start trigger for acquisition, etc.) for the engine to
configure the channel. Each channel has a set of *inputs* or *outputs*
associated with it (depending on whether it's an input or output channel). The
inputs and outputs act as the primary interface to the hardware for various
psiexpermient plugins. 

To illustrate how an engine might be configured in an Enaml manifest::

    NIDAQEngine:
        AOChannel:
            channel = 'Dev1/ao0'
            fs = 200e3
            ContinuousOutput:
                name = 'background'
            EpochOutput:
                name = 'target'
        AIChannel:
            channel = 'Dev1/ai0'
            fs = 200e3
            start_trigger = 'ao/StartTrigger'
            ContinuousInput:
                name = 'microphone'
        AIChannel:
            channel = 'Dev1/ai1'
            fs = 200e3
            start_trigger = 'ao/StartTrigger'

            IIRFilter:
                f_lowpass = 200
                btype = 'lowpass'
                ftype = 'butter'
                N = 4
                Downsample:
                    # effective Fs is 500
                    name = 'nose_poke_analog'
                    q = 400
                    Threshold:
                        threshold = 2.5
                        Edges:
                            debounce = 5
                            name = 'nose_poke'

        DOChannel:
            channel = 'Dev1/port0/line0'
            fs = 0
            Trigger:
                name = 'food_dispense_trigger'
                duration = 0.1    

An input channel can have a signal processing chain associated with
it that generates multiple inputs. For example, 'Dev/ai1' passes the input
through a low-pass filter, downsamples it from 200 kHz to 0.5 kHz, then
thresholds the filtered, downsampled signal to detect rising and falling edges
in the analog signal. If the input has a name, then it will automatically be
saved in the HDF5 file. So, the low-pass filtered signal at 200 kHz is *not*
saved because no name is associated with that stage in the processing chain.
However, the downsampled signal is saved as an array, `nose_poke_analog`.
Likewise, the edge detection stage generates nose-poke events that are
timestamped and stored in the event log.

To illustrate the flexibility of this signal chain, one could consider the
following input (presumably recording from a 16-channel electrode array). This
results in three signals (raw signal, low-pass filtered LFP and high-pass
filtered spike train)::

        AIChannel:
            channel = 'Dev2/ai0:16'
            fs = 25e3
            start_trigger = 'Dev2/PFI0'

            IIRFilter:
                f_lowpass = 200
                btype = 'lowpass'
                ftype = 'butter'
                N = 4
                name = 'lfp'

            IIRFilter:
                f_highpass = 300
                f_lowpass = 3000
                btype = 'bandpass'
                ftype = 'butter'
                N = 4
                name = 'spikes'

            Input:
                name = 'raw_signal'

Currently, an output channel may have multiple outputs defined (right now we
only support one ContinuousOutput and one EpochOutput per channel, but this may
be expanded in the future). This is not as well fleshed-out but is meant to
allow for the blending of multiple tokens into a single waveform that is sent
to the channel.

*To think about*

> Right now the Engine and Channel declarations are system-specific. One computer may have a different equipment configuration. The reason this works is because the various plugins in the psiexperiment ecosystem will look for named inputs and outputs. For example, to successfully use the food dispenser plugin, an output named `food_dispense_trigger` must exist. How the trigger is generated will be left up to the hardware-specific Engine implementation (the pump dispense trigger is driven by commands via the serial port).
    
> It seems that the inputs will need to be tied to the specific hardware system. This is particularly true for the inputs (e.g., some systems may have external hardware that converts the nose-poke signal to a binary value that is read in on a digital input channel rather than requiring that the thresholding be done in software). 

> In contrast, the outputs could theoretically be defined outside the hardware configuration. In this case, we would give the channels names (e.g., 'Dev1/ai0' would be named `speaker`). The output would then specify the channel name it is designed for::
    
    # Hypothetical restructuring of code to separate output and hardware configuration
    Extension:
        point = 'psi.controller.hardware'
        NIDAQEngine:
            AOChannel:
                channel = 'Dev1/ao0'
                fs = 200e3
                name = 'speaker1'
            DOChannel:
                channel = 'Dev1/port0/line0'
                fs = 0
        SerialPumpEngine:
            connection_url = 'COM3'
            Channel:
                # A fake channel, used to link the water dispense trigger. Maybe call it something else?
                name = 'water_dispense'
                
    Extension:
        point = 'psi.controller.io'
        ContinuousOutput:
            name = 'background'
            channel = 'speaker1'
        EpochOutput:
            name = 'target'
            channel = 'speaker1'
        Trigger:
            name = 'food_dispense_trigger'
            channel = 'food_dispense'
        Trigger:
            name = 'water_dispense_trigger'
            channel = 'water_dispense'


#### ExperimentAction

An *experiment action* is a command (configured in an Enaml plugin manifest)
that is invoked when a particular event occurs. The controller defines the
available events (e.g., `experiment_start`, `trial_start`, `reward`). As each
event occurs, all actions associated with that event will be triggered.

To illustrate how an action might be configured in an Enaml manifest::

    def dispense_pellet(event):
        controller = event.workbench.get_plugin('psi.controller')
        output = controller.get_output('food_dispense_trigger')
        output.fire()


    enamldef PelletDispenserManifest(PluginManifest):

        id = 'pellet_dispenser'

        Extension:
            id = 'commands'
            point = 'enaml.workbench.core.commands'
            Command:
                id = 'dispense_pellet'
                handler = dispense_pellet

        Extension:
            id = 'action'
            point = 'psi.controller.actions'
            ExperimentAction:
                event = 'deliver_reward'
                command = 'dispense_pellet'


Note how the `dispense_pellet` function will obtain the `food_dispense_trigger`
output from the controller. This is an example of how the plugin can remain
"agnostic" with respect to the actual hardware configuration.

*To think about*

> Right now I define the commands (i.e., the actual implementation) along with the association between an event and the corresponding command (i.e, the experiment action) in the same plugin. However, we should be able to break this into three parts: 1) A hardware interface (possibly defined as a subclass of Engine) that knows how to talk to a very specific piece of equipment, 2) a core set of commands that one would want to use regardless of the interface and 3) a behavioral paradigm-specific mapping of events to commands.

> To illustrate this, let's consider room light as an example. There are various ways we can have a room light be controlled via hardware. A room light is very simple. You either toggle it on or off. So, you would define an output:

    Toggle:
        name = 'room_light_toggle'
        channel = 'room_light'
        
> This output exists regardless of hardware implementation or what type of actions we would want to take regarding the room light. The toggle has two commands, `set_high` (i.e., turn on the light) and `set_low` (turn off the light). 

> Now, one could envision that a NI-DAQ card controls the room light via a relay using one of it's digital outputs. That's simple to configure the hardware definition:

    NIDAQEngine:
        DOChannel:
            channel = 'Dev1/port0/line0'
            name = 'room_light'
            fs = 0

> What if the computer somehow controls the room light via a serial port? 

    RoomLightSerialPortEngine:
        SerialChannel:
            name = 'room_light'
            
> The `DOChannel` or `SerialChannel` will know how to handle (in coordination with their parent engine) the `set_low` and `set_high` commands received from the toggle. We've achieved a little abstraction here. The final layer of abstraction is the mapping of events to commands. First, we would define the commands in a plugin manifest that could be loaded (the Toggle output can also be defined in this plugin manifest since it's intrinsically tied to the commands):

    def light_on(event):
        controller = event.workbench.get_plugin('psi.controller')
        output = controller.get_output('room_light_toggle')
        output.set_high()

    def light_off(event):
        controller = event.workbench.get_plugin('psi.controller')
        output = controller.get_output('room_light_toggle')
        output.set_low()
    
    Extension:
        point = 'enaml.core.workbench.commands'
        Command:
            id = 'psi.controller.room_light.turn_on'
            handler = light_on
        Command:
            id = 'psi.controller.room_light.turn_off'
            handler = light_off

    Extension:
        point = 'psi.controller.io'
        Toggle:
            name = 'room_light_toggle'
            channel = 'room_light'
            
> The hardware configuration would be defined in a separate file that is specific to the system psiexperiment is running on.

> Finally, we would have a paradigm-specific mapping of actions to commands. For an appetitive experiment (i.e., reward on correct responses), we would turn off the light when the animal receives a timeout. We can define this in a separate file:

    Extension:
        ponit = 'psi.controller.actions'
        ExperimentAction:
            event = 'timeout_start'
            command = 'psi.controller.room_light.turn_off'
        ExperimentAction:
            event = 'timeout_end'
            command = 'psi.controller.room_light.turn_on'


Plugins
-------

### Context plugin

Manages the context items and selectors (see terminology above).  Every
experiment has a set of values, or parameters, that define the course of the
experiment.  This plugin provides a central registry of all context items,
manages their current values (i.e., when notified, the current values will be
cleared and re-computed for the next trial).  A subset of these context items
can be specified as roving parameters (i.e., their value varies from trial to
trial in a predefined way). Values for roving parameters are managed by one or
more selectors.  Selectors are objects that provide a mechanism for specifying
the sequence of values that the context plugin draws from on each trial. 

### Experiment plugin

Provides basic management of the experiment workspace by managing GUI elements
provided by the loaded plugins (e.g., the context plugin provides several GUI
widgets) as well as providing methods to save/restore the layout of the
workspace as well as save/restore the preferences for each plugin.

### Data plugin

Provides basic management and analysis of data acquired during an experiment.

### Controller plugin

TODO


Roadmap
-------

TODO

Migrating from Neurobehavior 
----------------------------

This is a significant rewrite of Neurobehavior that leverages the strengths of
the Atom/Enaml framework. The key change is that Psiexperiment is plugin-based.
Writing experiments in Neurobehavior involved subclassing several classes
(e.g., paradigm, experiment, controller, data) and incorporating various mixins
(e.g., for the pump controller and pump data). Often this required some
cumbersome hacks to get the GUI and experiment to behave the way you want.
There were also some significant limitations with the context management system
(i.e., adding new parameters required subclassing the paradigm class and
possibly incorporating mixins for pumps, etc.). 

In contrast, setting up new experiments in psiexperiment should be simpler. You
decide the types of plugins you want loaded and write a manifest file that
defines the specific extensions you want. If you have a specific type of
analysis that you need done on the acquired data, you can write a new plugin
and load it.
