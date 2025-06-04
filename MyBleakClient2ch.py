import logging
import socket
from datetime import datetime, timedelta
from pathlib import Path

import aiofiles
from aiocsv import AsyncDictReader, AsyncDictWriter, AsyncReader, AsyncWriter
from bleak import BleakClient


try:
    from mu_interface.Utilities.utils import TimeFormat
except ImportError:
    class TimeFormat():
        file = '%Y-%m-%d_%H:%M:%S'
        log = '%d.%m.%Y. %H:%M:%S'
        data = '%Y-%m-%d %H:%M:%S:%f'


def array_split(array, n):
    """Split an array into n equal parts."""
    split, rem = divmod(len(array), n)
    if rem != 0:
        raise ValueError(f"Array length {len(array)} is not divisible by {n}.")

    list_of_arrays = []
    for i in range(n):
        list_of_arrays.append(array[i * split:(i + 1) * split])

    return list_of_arrays


def mean(array):
    """Calculate the mean of an array."""
    return sum(array) / len(array)

class MyBleakClient(BleakClient):
    def __init__(self, device, OB_active, **kwargs):
        super().__init__(device, **kwargs)
        self.device = device

        # for local testing on a raspberry pi
        if OB_active:
            with open("/home/rock/OrangeBox/status/experiment_number.txt", "r") as f:
                experiment_number = int(f.read())
            self.experiment_name = f"{socket.gethostname()}_{experiment_number}"
            self.file_path = Path.home() / 'measurements' / self.experiment_name / 'BLE' / self.device.name
            self.file_name_prefix = f"{self.experiment_name}_{self.device.name}"
        else:
            self.file_path = Path('/home/pi/Desktop/measurment', self.device.name)
            self.file_name_prefix = f"{self.device.name}"
        self.file_name = f"{self.file_name_prefix}_{datetime.now().strftime(TimeFormat.file)}.csv"
        self.avg_file_name = f"ZZ_AVG_PLOTTING_{self.device.name}_IGNORE_ME.csv"

        ## CSV - new
        Path(self.file_path).mkdir(parents=True, exist_ok=True)  # make new directory

        # Data fields are loaded in their original order by default
        # and we always want to add our timestamp.
        self.header = ["datetime", "CH1", "CH2"]  #'differential_potential']
        self.last_csv_time = datetime.now()

        # Stuff for averaging high frequency data to lower frequency for live plotting
        self.avg_buffer_len = 10
        self.avg_buffer_idx = 0
        self.avg_buffer = [[0.0] * self.avg_buffer_len, [0.0] * self.avg_buffer_len]
        self.avg_lines_to_copy = 120 * 60  # 120 minutes of data
        self.avg_first_write = True

        self.current_time = None
        self.last_time = None

    async def write2csv_io(self, data, freq):
        # data is the array of every data (3 bytes each) so 66 entries
        # first 33 are ch0, last 33 are ch1, need to split
        temp = array_split(data, 2)
        data0 = temp[0]
        data1 = temp[1]

        # Create new file every 12 hours
        self.current_time = datetime.now()
        if self.current_time.hour in {0,12} and self.current_time.hour != self.last_csv_time.hour:
            self.last_csv_time = datetime.now()
            self.file_name = f"{self.file_name_prefix}_{datetime.now().strftime(TimeFormat.file)}.csv"
            self.avg_first_write = True
            logging.info("Creating a new csv file.")
            self.last_time = None

        async with aiofiles.open(self.file_path / self.file_name, mode="a+") as f:
            csvwriter = AsyncWriter(f)
            # times gets the time for every data entry
            # ch0 and ch1 should be at the same time, so only need to use one of them for timing
            times = []

            if self.last_time is None:
                await csvwriter.writerow(self.header)
                time_delta = timedelta(milliseconds=1 / freq * 1000)
            else:
                time_delta = (self.current_time - self.last_time) / len(data0)

            # calculating the time for each data entry starting from the last one
            # only need for 1 channel since they are measured at same time
            for i in range(len(data0)):
                times_string = (self.current_time - i*time_delta).strftime(TimeFormat.data)
                times.append(times_string)

            times.reverse()  # need to reverse because calcuated times backwards
            combined_list = [[x, y, z] for x, y, z in zip(times, data0, data1)]
            self.last_time = self.current_time

            await csvwriter.writerows(combined_list)
        """
        # Averaging for live plotting
        self.avg_buffer[0][self.avg_buffer_idx] = mean(data0)
        self.avg_buffer[1][self.avg_buffer_idx] = mean(data1)
        self.avg_buffer_idx += 1

        try:
            if self.avg_first_write:
                await self.reset_avarage_file()
                self.avg_first_write = False

            if self.avg_buffer_idx == self.avg_buffer_len:
                self.avg_buffer_idx = 0
                async with aiofiles.open(self.file_path / self.avg_file_name, mode="a+") as f:
                    avg_csvwriter = AsyncWriter(f)
                    await avg_csvwriter.writerow([self.current_time.strftime(TimeFormat.data),
                                                round(mean(self.avg_buffer[0])),
                                                round(mean(self.avg_buffer[1]))])
        except Exception as e:
            logging.error(f"Error in writing to or resetting the average file: {e}")

    async def reset_avarage_file(self):
        content = []
        if (self.file_path / self.avg_file_name).exists():
            async with aiofiles.open(self.file_path / self.avg_file_name, 'r') as f:
                async for row in AsyncReader(f):
                    if row != self.header:
                        content.append(row)

        async with aiofiles.open(self.file_path / self.avg_file_name, 'w') as f:
            avg_csvwriter = AsyncWriter(f)
            await avg_csvwriter.writerow(self.header)
            await avg_csvwriter.writerows(content[-self.avg_lines_to_copy:])
        """
