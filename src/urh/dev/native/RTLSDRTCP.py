from multiprocessing import Value

import numpy as np

from urh.dev.native.Device import Device
from urh.util.Logger import logger

import socket

class RTLSDRTCP(Device):
    BYTES_PER_SAMPLE = 2  # RTLSDR device produces 8 bit unsigned IQ data
    MAXDATASIZE = 65536
    ENDIAN = "big"
    RTL_TCP_CONSTS = ["NULL", "centerFreq", "sampleRate", "tunerGainMode", "tunerGain", "freqCorrection", "tunerIFGain",
                      "testMode", "agcMode", "directSampling", "offsetTuning", "rtlXtalFreq", "tunerXtalFreq",
                      "gainByIndex", "bandwidth", "biasTee"]

    def receive_sync(self, data_connection, ctrl_connection, device_number: int, center_freq: int, sample_rate: int,
                     gain: int):
        self.open("127.0.0.1", 1234)
        self.device_number = device_number
        self.set_parameter("centerFreq", center_freq)
        self.set_parameter("sampleRate", sample_rate)
        self.set_parameter("tunerGain", gain)
        exit_requested = False

        while not exit_requested:
            while ctrl_connection.poll():
                result = self.process_command(ctrl_connection.recv())
                if result == "stop":
                    exit_requested = True
                    break

            if not exit_requested:
                data_connection.send_bytes(self.read_sync())

        logger.debug("RTLSDRTCP: closing device")
        ret = self.close()
        ctrl_connection.send("close:" + str(ret))
        data_connection.close()
        ctrl_connection.close()

    def process_command(self, command):
        logger.debug("RTLSDRTCP: {}".format(command))
        if command == "stop":
            return "stop"

        tag, value = command.split(":")
        if tag == "center_freq":
            logger.info("RTLSDRTCP: Set center freq to {0}".format(int(value)))
            return self.set_parameter("centerFreq", int(value))

        elif tag == "tuner_gain":
            logger.info("RTLSDRTCP: Set tuner gain to {0}".format(int(value)))
            return self.set_parameter("tunerGain", int(value))

        elif tag == "sample_rate":
            logger.info("RTLSDRTCP: Set sample_rate to {0}".format(int(value)))
            return self.set_parameter("sampleRate", int(value))

        elif tag == "tuner_bandwidth":
            logger.info("RTLSDRTCP: Set bandwidth to {0}".format(int(value)))
            return self.set_parameter("bandwidth", int(value))

    def __init__(self, freq, gain, srate, device_number, is_ringbuffer=False):
        super().__init__(0, freq, gain, srate, is_ringbuffer)

        self.socket_is_open = False
        self.open("127.0.0.1", 1234)
        self.success = 0
        self.is_receiving_p = Value('i', 0)
        """
        Shared Value to communicate with the receiving process.

        """
        self._max_frequency = 6e9
        self._max_sample_rate = 3200000
        self._max_frequency = 6e9
        self._max_bandwidth = 3200000
        self._max_gain = 500  # Todo: Consider get_tuner_gains for allowed gains here

        self.device_number = device_number

    @property
    def receive_process_arguments(self):
        return self.child_data_conn, self.child_ctrl_conn, self.device_number, self.frequency, self.sample_rate, self.gain

    def open(self, hostname="127.0.0.1", port=1234):
        if not self.socket_is_open:
            try:
                # Create socket and connect
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
                self.sock.settimeout(1.0)   # Timeout 1s
                self.sock.connect((hostname, port))

                # Receive rtl_tcp initial data
                init_data = self.sock.recv(self.MAXDATASIZE)

                if len(init_data) != 12:
                    return False
                if init_data[0:4] != b'RTL0':
                    return False

                # Extract tuner name
                tuner_number = int.from_bytes(init_data[4:8], self.ENDIAN)
                if tuner_number == 1:
                    self.tuner = "E4000"
                elif tuner_number == 2:
                    self.tuner = "FC0012"
                elif tuner_number == 3:
                    self.tuner = "FC0013"
                elif tuner_number == 4:
                    self.tuner = "FC2580"
                elif tuner_number == 5:
                    self.tuner = "R820T"
                elif tuner_number == 6:
                    self.tuner = "R828D"
                else:
                    self.tuner = "Unknown"

                # Extract IF and RF gain
                self.if_gain = int.from_bytes(init_data[8:10], self.ENDIAN)
                self.rf_gain = int.from_bytes(init_data[10:12], self.ENDIAN)

                self.socket_is_open = True
            except OSError as e:
                self.socket_is_open = False
                logger.info("Could not connect to rtl_tcp", hostname, port, "(", str(e), ")")

    def close(self):
        if self.socket_is_open:
            self.socket_is_open = False
        return self.sock.close()

    def set_parameter(self, param, value):  # returns error (True/False)
        msg = self.RTL_TCP_CONSTS.index(param).to_bytes(1, self.ENDIAN)     # Set param at bits 0-7
        msg += value.to_bytes(4, self.ENDIAN)   # Set value at bits 8-39

        print("set:", param, value)

        try:
            self.sock.sendall(msg)  # Send data to rtl_tcp
        except OSError as e:
            self.sock.close()
            logger.info("Could not set parameter", param, value, msg, "(", str(e), ")")
            return True

        return False

    def read_sync(self):
        # returns data directly, unpack?
        return self.sock.recv(self.MAXDATASIZE)

    def set_device_frequency(self, frequency):
        error = self.set_parameter("centerFreq", int(frequency))
        self.log_retcode(error, "Set center frequency")
        return error

    def set_device_sample_rate(self, sample_rate):
        error = self.set_parameter("sampleRate", int(sample_rate))
        self.log_retcode(error, "Set sample rate")
        return error

    def set_freq_correction(self, ppm):
        error = self.set_parameter("freqCorrection", int(ppm))
        self.log_retcode(error, "Set frequency correction")
        return error

    def set_offset_tuning(self, on: bool):
        error = self.set_parameter("offsetTuning", on)
        self.log_retcode(error, "Set offset tuning")
        return error

    def set_gain_mode(self, manual: bool):
        error = self.set_parameter("tunerGainMode", manual)
        self.log_retcode(error, "Set gain mode manual")
        return error

    def set_if_gain(self, gain):
        error = self.set_parameter("tunerIFGain", int(gain))
        self.log_retcode(error, "Set IF gain")
        return error

    def set_gain(self, gain):
        error = self.set_parameter("tunerGain", int(gain))
        self.log_retcode(error, "Set tuner gain")
        return error

    def set_bandwidth(self, bandwidth):
        error = self.set_parameter("bandwidth", int(bandwidth))
        self.log_retcode(error, "Set tuner bandwidth")
        return error

    @staticmethod
    def unpack_complex(buffer, nvalues: int):
        """
        The raw, captured IQ data is 8 bit unsigned data.

        :return:
        """
        result = np.empty(nvalues, dtype=np.complex64)
        unpacked = np.frombuffer(buffer, dtype=[('r', np.uint8), ('i', np.uint8)])
        result.real = (unpacked['r'] / 127.5) - 1.0
        result.imag = (unpacked['i'] / 127.5) - 1.0
        return result

    @staticmethod
    def pack_complex(complex_samples: np.ndarray):
        return (127.5 * (complex_samples.view(np.float32) + 1.0)).astype(np.uint8).tostring()