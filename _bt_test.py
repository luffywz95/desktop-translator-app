import asyncio
from winsdk.windows.devices.enumeration import DeviceInformation
from winsdk.windows.devices.bluetooth import BluetoothDevice


async def main():
    selector = BluetoothDevice.get_device_selector()
    infos = await DeviceInformation.find_all_async(selector, [])
    print("count", len(infos))
    for info in infos[:5]:
        print(info.name, info.id)


asyncio.run(main())
