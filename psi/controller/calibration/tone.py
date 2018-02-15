import logging
log = logging.getLogger(__name__)

from functools import partial
import time

import numpy as np
import pandas as pd

from .util import tone_power_conv, db
from ..util import acquire
from . import (FlatCalibration, PointCalibration, CalibrationTHDError,
               CalibrationNFError)
from ..queue import FIFOSignalQueue
from ..output import QueuedEpochOutput
from ..input import ExtractEpochs


from psi.token.primitives import (tone_factory, silence_factory,
                                  generate_waveform)


thd_err_mesg = 'Total harmonic distortion for {}Hz is {}%'
nf_err_mesg = 'Power at {}Hz has SNR of {}dB'


def process_tone(fs, signal, frequency, min_snr=None, max_thd=None,
                 thd_harmonics=3, silence=None):
    '''
    Compute the RMS at the specified frequency. Check for distortion.

    Parameters
    ----------
    fs : float
        Sampling frequency of signal
    signal : ndarray
        Last dimension must be time. If more than one dimension, first
        dimension must be repetition.
    frequency : float
        Frequency (Hz) to analyze
    min_snr : {None, float}
        If specified, must provide a noise floor measure (silence). The ratio,
        in dB, of signal RMS to silence RMS must be greater than min_snr. If
        not, a CalibrationNFError is raised.
    max_thd : {None, float}
        If specified, ensures that the total harmonic distortion, as a
        percentage, is less than max_thd. If not, a CalibrationTHDError is
        raised.
    thd_harmonics : int
        Number of harmonics to compute. If you pick too many, some harmonics
        may be above the Nyquist frequency and you'll get an exception.
    thd_harmonics : int
        Number of harmonics to compute. If you pick too many, some harmonics
        may be above the Nyquist frequency and you'll get an exception.
    silence : {None, ndarray}
        Noise floor measurement. Required for min_snr. Shape must match signal
        in all dimensions except the first and last.

    Returns
    -------
    result : pandas Series
        Series containing rms, snr, thd and frequency.
    '''
    harmonics = frequency * (np.arange(thd_harmonics) + 1)

    # This returns an array of [harmonic, repetition, channel]. Here, rms[0] is
    # the rms at the fundamental frequency. rms[1:] is the rms at all the
    # harmonics.
    signal = np.atleast_2d(signal)
    rms = tone_power_conv(signal, fs, harmonics, 'flattop')

    # Compute the mean RMS at F0 across all repetitions
    rms = rms.mean(axis=1)
    freq_rms = rms[0]

    # Compute the harmonic distortion as a percent
    thd = np.sqrt(np.sum(rms[1:]**2))/freq_rms * 100

    if min_snr is not None:
        silence = np.atleast_2d(silence)
        noise_rms = tone_power_conv(silence, fs, frequency, 'flattop')
        noise_rms = noise_rms.mean(axis=0)
        freq_snr = db(freq_rms, noise_rms)
        if np.any(freq_snr < min_snr):
            mesg = nf_err_mesg.format(frequency, freq_snr)
            raise CalibrationNFError(mesg)
    else:
        freq_snr = np.full_like(freq_rms, np.nan)

    if max_thd is not None and np.any(thd > max_thd):
        mesg = thd_err_mesg.format(frequency, thd)
        raise CalibrationTHDError(mesg)

    # Concatenate and return as a record array
    result = np.concatenate((freq_rms[np.newaxis],
                             freq_snr[np.newaxis],
                             thd[np.newaxis]))

    return pd.Series({'rms': freq_rms,
                      'snr': freq_snr,
                      'thd': thd,
                      })


def tone_power(engine, frequencies, ao_channel_name, ai_channel_names, gain=0,
               vrms=1, repetitions=2, min_snr=None, max_thd=None, thd_harmonics=3,
               duration=0.1, trim=0.01, iti=0.01):
    '''
    Given a single output, measure response in multiple input channels.

    Parameters
    ----------
    TODO

    Returns
    -------
    result : pandas DataFrame
        Dataframe will be indexed by output channel name and frequency. Columns
        will be rms (in V), snr (in DB) and thd (in percent).
    '''

    frequencies = np.asarray(frequencies)
    calibration = FlatCalibration.as_attenuation(vrms=vrms)

    # Create a copy of the engine containing only the channels required for
    # calibration.
    channel_names = ai_channel_names + [ao_channel_name]
    cal_engine = engine.clone(channel_names)
    ao_channel = cal_engine.get_channel(ao_channel_name)
    ai_channels = [cal_engine.get_channel(name) for name in ai_channel_names]

    ao_fs = ao_channel.fs
    ai_fs = ai_channels[0].fs

    # Build the signal queue
    queue = FIFOSignalQueue(ao_fs)
    for frequency in frequencies:
        factory = tone_factory(ao_fs, gain, frequency, 0, 1, calibration)
        waveform = generate_waveform(factory, int(duration*ao_fs))
        queue.append(waveform, repetitions, iti)

    factory = silence_factory(ao_fs, calibration)
    waveform = generate_waveform(factory, int(duration*ao_fs))
    queue.append(waveform, repetitions, iti)

    # Add the queue to the output channel
    ao_channel.add_queued_epoch_output(queue, auto_decrement=True)

    # Attach the input to the channel
    data = [[]] * len(ai_channels)

    def accumulate(epochs, epoch):
        epochs.extend(epoch)

    for i, ai_channel in enumerate(ai_channels):
        cb = partial(accumulate, data[i])
        epoch_input = ExtractEpochs(queue=queue, epoch_size=duration+iti)
        epoch_input.add_callback(cb)
        ai_channel.add_input(epoch_input)

    cal_engine.start()
    while not epoch_input.complete:
        time.sleep(0.1)
    cal_engine.stop()

    result = []
    for channel, channel_data in zip(ai_channels, data):
        # Process data from channel
        epochs = [epoch['signal'][np.newaxis] for epoch in channel_data]
        signal = np.concatenate(epochs)
        signal.shape = [-1, repetitions] + list(signal.shape[1:])

        # Loop through each frequency (silence will always be the last one)
        silence = signal[-1]
        signal = signal[:-1]
        channel_result = []
        for f, s in zip(frequencies, signal):
            f_result = process_tone(channel.fs, s, f, min_snr, max_thd,
                                    thd_harmonics, silence)
            f_result['frequency'] = f
            channel_result.append(f_result)
        df = pd.DataFrame(channel_result)
        df['channel_name'] = channel.name
        result.append(df)

    return pd.concat(result).set_index(['channel_name', 'frequency'])


def tone_spl(engine, *args, **kwargs):
    '''
    Given a single output, measure resulting SPL in multiple input channels.

    Parameters
    ----------
    TODO

    Returns
    -------
    result : pandas DataFrame
        Dataframe will be indexed by output channel name and frequency. Columns
        will be rms (in V), snr (in DB), thd (in percent) and spl (measured dB
        SPL according to the input calibration).
    '''
    result = tone_power(engine, *args, **kwargs)

    def map_spl(series, engine):
        channel_name, frequency = series.name
        channel = engine.get_channel(channel_name)
        spl = channel.calibration.get_spl(frequency, series['rms'])
        series['spl'] = spl
        return series

    return result.apply(map_spl, axis=1, args=(engine,))


def tone_sens(engine, frequencies, gain=-40, vrms=1, *args, **kwargs):
    '''
    Given a single output, measure sensitivity of output based on multiple
    input channels.

    Parameters
    ----------
    TODO

    Returns
    -------
    result : pandas DataFrame
        Dataframe will be indexed by output channel name and frequency. Columns
        will be rms (in V), snr (in DB), thd (in percent), spl (measured dB
        SPL according to the input calibration) norm_spl (the output, in dB
        SPL, that would be generated assuming the tone is 1 VRMS and gain is 0)
        and sens (sensitivity of output in dB(V/Pa)). These values are reported
        separately for each input. Although the dB SPL, normalized SPL and
        sensitivity of the output as measured by each input should agree, there
        will be some equipment error. So, either average them together or
        choose the most trustworthy input.
    '''
    kwargs.update(dict(gain=gain, vrms=vrms))
    result = tone_spl(engine, frequencies, *args, **kwargs)
    result['norm_spl'] = result['spl'] - gain - db(vrms)
    result['sens'] = -result['norm_spl']-db(20e-6)
    return result


def tone_calibration(engine, frequencies, *args, **kwargs):
    '''
    Single output calibration at a fixed frequency
    Returns
    -------
    sens : dB (V/Pa)
        Sensitivity of output in dB (V/Pa).
    '''
    output_sens = tone_sens(engine, frequencies, *args, **kwargs)[0]
    return PointCalibration(frequencies, output_sens)
