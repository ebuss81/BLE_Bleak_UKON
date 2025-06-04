import csv
import logging
import socket
from datetime import datetime, timedelta
from pathlib import Path

import aiofiles
import numpy
from aiocsv import AsyncDictReader, AsyncDictWriter, AsyncReader, AsyncWriter
from bleak import BleakClient



try:
    from mu_interface.Utilities.utils import TimeFormat
except ImportError:
    class TimeFormat():
        file = '%Y-%m-%d_%H:%M:%S'
        log = '%d.%m.%Y. %H:%M:%S'
        data = '%Y-%m-%d %H:%M:%S:%f'


class MyBleakClient(BleakClient):
    def __init__(self, device,OB_active, **kwargs, ):
        super().__init__(device, **kwargs)
        self.device = device

        # for local testing on a raspberry pi
        if OB_active:
            with open("/home/rock/OrangeBox/status/experiment_number.txt", "r") as f:
                experiment_number = int(f.read())
            self.experiment_name = f"{socket.gethostname()}_{experiment_number}"
            self.file_path = Path.home() / 'measurements' / self.experiment_name / 'BLE' / self.device.name
            self.file_name = f"{self.experiment_name}_{self.device.name}_{datetime.now().strftime(TimeFormat.file)}.csv"
        else:
            self.file_path = Path('/home/pi/Desktop/measurement', self.device.name)
            self.file_name = f"{self.device.name}_{datetime.now().strftime(TimeFormat.file)}.csv"

        ## CSV - new
        Path(self.file_path).mkdir(parents=True, exist_ok=True)  # make new directory

        # Data fields are loaded in their original order by default
        # and we always want to add our timestamp.
        self.header = ["datetime", "CH1", "CH2"]  #'differential_potential']
        self.last_csv_time = datetime.now()

        self.first_value = True
        self.current_time = None
        self.last_time = None
        if OB_active:
            self.status_dir = Path("/home/rock/OrangeBox/status/measuring")
            self.status_dir.mkdir(parents=True, exist_ok=True)
            self.csvfile1 = open(self.status_dir / self.device.name, 'a+')
            self.csvfile1.close()

    async def write2csv_io(self, data, freq):
        # try:
        # data is the array of every data (3 bytes each) so 66 entries
        # first 33 are ch0, last 33 are ch1, need to split
        temp = numpy.array_split(data, 2)
        data0 = temp[0]
        data1 = temp[1]

        self.current_time = datetime.now()
        if self.current_time.hour in {0,12} and self.current_time.hour != self.last_csv_time.hour:  # create new file every 12 hours
            # self.csvfile.close()
            self.last_csv_time = datetime.now()
            self.file_name = f"{self.device.name}_{datetime.now().strftime(TimeFormat.file)}.csv"
            logging.info("Creating a new csv file.")
            self.first_value = True

        # self.csvfile = open(self.file_path + self.file_name, 'a+')
        async with aiofiles.open(self.file_path / self.file_name, mode="a+") as f:
            self.csvwriter = AsyncWriter(f)
            # times gets the time for every data entry
            # ch0 and ch1 should be at the same time, so only need to use one of them for timing
            times = []
            # TODO: condense if/else
            if self.first_value:
                await self.csvwriter.writerow(self.header)
                # print("header written")
                t_delta = 1 / freq * 1000
                time_delta = timedelta(milliseconds=t_delta)
                # calculating the time for each data entry starting from the last one
                # only need for 1 channel since they are measured at same time
                for i in range(len(data0)):
                    times_string = (self.current_time - i*time_delta).strftime(TimeFormat.data)
                    times.append(times_string)
                times.reverse()
                # ^ need to reverse because calcuated times backwards
                combined_list = [[x, y, z] for x, y, z in zip(times, data0, data1)]
                self.first_value = False
                self.last_time = self.current_time
            else:
                # print(self.current_time-self.last_time, self.current_time, self.last_time)
                t_delta = (self.current_time - self.last_time) / len(data0)
                # time_delta = timedelta(t_delta)
                for i in range(len(data0)):
                    times_string = (self.current_time - i*t_delta).strftime(TimeFormat.data)
                    times.append(times_string)
                times.reverse()
                combined_list = [[x, y, z] for x, y, z in zip(times, data0, data1)]
                self.last_time = self.current_time
            data4csv = combined_list
            #print(data4csv)

            await self.csvwriter.writerows(data4csv)
            # self.csvfile.close()
