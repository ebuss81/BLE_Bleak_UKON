import asyncio
import logging
from datetime import datetime
from functools import partial
import argparse

from bleak import BleakClient, BleakScanner, BLEDevice
from MyBleakClient2ch import MyBleakClient


try:
    from mu_interface.Utilities.log_formatter import setup_logger, log_DBGX
except ImportError:
    def setup_logger(name, level=logging.INFO):
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    log_DBGX = 15


NOTIFICATION_UUID = "5a3b0203-f6dd-4c45-b31f-e89c05ae3390"


async def discoverNodes(name):  # -> BLEDevice | None:
    """
    Discovering devices and return object of device
    """
    logging.info("scanning...")
    devices = await BleakScanner.discover()
    for d in devices:
        if d.name == name:
            logging.info(d.details)
            return d
    return None


async def conectToNode(lock, name, OB_activate):  # -> BleakClient | None:
    """
    Finds device with device name and connects to it
    """
    async with lock:
        logging.info(f"Connecting to device with name: {name}")
        device = await BleakScanner.find_device_by_name(name)
    if not device:
        logging.error(f"FAILED connection to device with name: {name}")
        return None, None

    client = MyBleakClient(device, OB_active = OB_activate, disconnected_callback=disconnected_callback)
    # Modification: Check if the client is already connected TODO: new
    if client.is_connected:
        logging.info(f"Already connected to {name}")
        return device, client

    await client.connect()
    if client.is_connected:
        logging.info(f"Connected to device with name: {name}")
        return device, client
    else:
        logging.error(f"FAILED connection to device with name: {name}")
        return None, None


async def notification_callback_handler(sender, data):
    print("Read:", int.from_bytes(data, "big"))


async def my_notification_callback_with_client_input(client, sender: int, data: bytearray):
    """Notification callback with client awareness"""
    singl_val = [data[i : i + 3] for i in range(0, len(data), 3)]
    #data = int.from_bytes(data, "big")
    real_val = [int.from_bytes(d, "big") for d in singl_val]
    #name = client.device.name
    await client.write2csv_io(real_val, 200)



def disconnected_callback(client: BleakClient):
    logging.info(f"{client.address} disconnected")


def getVolt(data):
    Vref = 2.5
    Gain = 4
    databits = 8388608

    volt = data / databits
    volt1 = volt - 1
    volt2 = volt1 * Vref / Gain
    return volt2 * 1000


async def NotificationRoutine(lock, device_name, OB_activate):
    client = None
    while True:
        if not client:
            try:
                connection_task = asyncio.create_task(conectToNode(lock, device_name, OB_activate))
                device, client = await connection_task
                await asyncio.sleep(2)  # Short delay before attempting notifications TODO: new
            except Exception as e:
                logging.error(f"{device_name} connection error: {e}")
                await asyncio.sleep(5)  # Add delay before retrying   TODO: new
                continue
        try:
            await client.start_notify(NOTIFICATION_UUID, partial(my_notification_callback_with_client_input, client))
            while (client.is_connected):
                await asyncio.sleep(1)
        except Exception as e:
            logging.error(f"Error has occured: {e}")
            device = None
            client = None


async def main():
    parser = argparse.ArgumentParser(
        description="Activate Orange Box integeration"
    )
    parser.add_argument("--OB_activate", required=True, type=int)
    args = parser.parse_args()

    device_names = ['P1']
    lock = asyncio.Lock()
    device = await asyncio.gather(*(NotificationRoutine(lock,name,args.OB_activate) for name in device_names))



if __name__ == "__main__":
    logging.addLevelName(log_DBGX, "DEBUG")
    setup_logger("BLE Interface", log_DBGX)
    
    asyncio.run(main())
    """
    for i in range(100):
        for attempt in range(10):
            try:
                asyncio.run(main())
            except:
            # perhaps reconnect, etc.
                pass
            else:
                break
        else:
    # we failed all the attempts - deal with the consequences.
            tasks = asyncio.all_tasks()
            for t in tasks:
                t.cancel()
                print("CANCELLED", t)
    """
