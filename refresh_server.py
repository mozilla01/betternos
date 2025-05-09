from betternos.utils import refresh_servers, get_servers
import os
import json
import time
import asyncio

interval = 5  # seconds

async def refresh_servers(db):
    while True:
        print('Reading servers.json')
        servers = await get_servers()
        print('Refreshing servers.json')
        refreshed_servers = refresh_servers(servers)
        print('Writing servers.json')
        for server in refreshed_servers:
            print(f"Server: {server['name']}, IP: {server['ip']}, PID: {server['pid']}, Running: {server['running']}")
            await db.execute(
                "UPDATE servers SET running = :running, pid = :pid WHERE id = :id",
                {
                    'running': server['running'],
                    'pid': server['pid'],
                    'id': server['id']
                }
            )
        print('-------------------------------')
        time.sleep(interval)
        
if __name__ == "__main__":
    from main import get_db
    asyncio.run(refresh_servers)