import os
import can
import logging
from datetime import datetime
from can.io.asc import ASCWriter

class CANLogger:
    def __init__(self, channel='can0', interface='socketcan', can_fd= True, filters=None,log_dir=None):
        """
        Initializes the CANLogger with the provided CAN interface settings
        and log directory.
        """
        self.channel = channel
        self.interface = interface
        self.can_fd = can_fd
        self.log_dir = log_dir
        self.filters = filters

        self.bus = None
        self.notifier = None
        self.writer = None
        self.file = None
        self.log_path = None

    def _open_bus(self):
        bus_kwargs = {
            "channel": self.channel,
            "bustype": self.interface,
            "can_filters": self.filters,
            "fd": self.can_fd,
        }

        # SocketCAN can otherwise depend on interface loopback defaults for Tx capture.
        # Requesting own messages makes the ASC logger product-safe for our tester frames.
        try:
            return can.interface.Bus(**bus_kwargs, receive_own_messages=True)
        except TypeError:
            logging.warning(
                "[CANLogger] Backend does not support receive_own_messages; "
                "falling back to default bus creation"
            )
            return can.interface.Bus(**bus_kwargs)

    def start(self,filename=None):
        """
        Start CAN bus logging with ASCWriter attached to notifier.
        Writes ASC log header manually to match Vector format.
        """
        if self.notifier or self.writer:
            self.stop()

        os.makedirs(self.log_dir, exist_ok=True)

        # Create timestamped log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        #self.log_path = os.path.join(self.log_dir, f"can_log_{timestamp}.asc")
        self.log_path = os.path.join(self.log_dir, filename)

        try:
            # Open log file for writing
            self.file = open(self.log_path, 'w', buffering=1, encoding='utf-8', newline='')
            '''
            # Write ASC-style header
            self.file.write(f'date {datetime.now().strftime("%Y-%m-%d")}\n')
            self.file.write('base hex timestamps absolute\n')
            self.file.write('comment: Logging CAN communication\n')
            self.file.write('begin of logfile\n')
            '''

            # Create CAN bus interface
            self.bus = self._open_bus()

            # Attach ASCWriter to bus via Notifier
            self.writer = ASCWriter(self.file)
            self.notifier = can.Notifier(self.bus, [self.writer])
            self.file.flush()

            logging.info(f"CAN logging started: {self.log_path}")

        except Exception as e:
            logging.error(f"[CANLogger] Failed to start: {e}")

    def stop(self):
        """
        Stops logging and writes ASC footer.
        """
        try:
            if self.notifier:
                self.notifier.stop()
                self.notifier = None

            if self.writer:
                self.writer.stop()
                self.writer = None

            if self.file:
                self.file.flush()
                self.file.write('end of logfile\n')
                self.file.flush()
                os.fsync(self.file.fileno())
                self.file.close()
                self.file = None

            if self.bus:
                try:
                    self.bus.shutdown()
                except Exception as exc:
                    logging.warning(f"[CANLogger] Bus shutdown warning: {exc}")

            logging.info(f"CAN logging stopped: {self.log_path}")
            print(f"[CANLogger] Log file saved to: {self.log_path}")

        except Exception as e:
            logging.error(f"[CANLogger] Error during stop: {e}")

        # Reset
        self.bus = None

    def get_log_path(self):
        """
        Returns the path to the current log file.
        """
        return self.log_path
