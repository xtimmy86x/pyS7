"""Async S7 client demo.

Shows how to use AsyncS7Client for non-blocking PLC communication
with asyncio.

Usage:
    python async_client_demo.py
"""

import asyncio

from pyS7 import AsyncS7Client


async def basic_read_write():
    """Basic async read and write operations."""
    async with AsyncS7Client(address="192.168.5.100", rack=0, slot=1) as client:
        # Read multiple tags
        values = await client.read(["DB1,I0", "DB1,R4", "DB1,X0.0"])
        print(f"Read values: {values}")

        # Write values
        await client.write(["DB1,I0", "DB1,R4"], [42, 3.14])
        print("Write complete")


async def detailed_operations():
    """Per-tag error handling with read_detailed / write_detailed."""
    async with AsyncS7Client(address="192.168.5.100", rack=0, slot=1) as client:
        # read_detailed continues on errors
        results = await client.read_detailed(["DB1,I0", "DB99,I0", "DB1,R4"])
        for r in results:
            if r.success:
                print(f"  {r.tag}: {r.value}")
            else:
                print(f"  {r.tag} FAILED: {r.error}")

        # write_detailed returns per-tag results
        write_results = await client.write_detailed(
            ["DB1,I0", "DB1,I2"], [100, 200]
        )
        for r in write_results:
            status = "OK" if r.success else r.error
            print(f"  {r.tag}: {status}")


async def batch_write_example():
    """Transactional batch write with automatic rollback."""
    async with AsyncS7Client(address="192.168.5.100", rack=0, slot=1) as client:
        # Auto-commit: writes on exit, rolls back on error
        async with client.batch_write() as batch:
            batch.add("DB1,I0", 100)
            batch.add("DB1,I2", 200)
            batch.add("DB1,R4", 3.14)

        print("Batch write committed")


async def cpu_diagnostics():
    """Read CPU status and info."""
    async with AsyncS7Client(address="192.168.5.100", rack=0, slot=1) as client:
        status = await client.get_cpu_status()
        print(f"CPU Status: {status}")

        info = await client.get_cpu_info()
        print(f"Model: {info['module_type_name']}")
        print(f"Firmware: {info['firmware_version']}")


async def concurrent_polling():
    """Multiple coroutines sharing a single client."""

    async def poll(client, tag, count=5):
        for _ in range(count):
            value = (await client.read([tag]))[0]
            print(f"  {tag} = {value}")
            await asyncio.sleep(0.5)

    async with AsyncS7Client(address="192.168.5.100", rack=0, slot=1) as client:
        await asyncio.gather(
            poll(client, "DB1,I0"),
            poll(client, "DB1,R4"),
        )


async def multiple_plcs():
    """Connect to multiple PLCs concurrently."""

    async def read_plc(address, tags):
        async with AsyncS7Client(address, 0, 1) as client:
            return await client.read(tags)

    results = await asyncio.gather(
        read_plc("192.168.0.1", ["DB1,I0"]),
        read_plc("192.168.0.2", ["DB1,I0"]),
        return_exceptions=True,
    )
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"  PLC {i+1}: Error - {result}")
        else:
            print(f"  PLC {i+1}: {result}")


async def main():
    print("=== Basic Read/Write ===")
    await basic_read_write()

    print("\n=== Detailed Operations ===")
    await detailed_operations()

    print("\n=== Batch Write ===")
    await batch_write_example()

    print("\n=== CPU Diagnostics ===")
    await cpu_diagnostics()

    print("\n=== Concurrent Polling ===")
    await concurrent_polling()

    print("\n=== Multiple PLCs ===")
    await multiple_plcs()


if __name__ == "__main__":
    asyncio.run(main())
