from betternos.utils import refresh_servers, get_servers
import time
import asyncio
from betternos.db import SessionLocal, engine, Base
from sqlalchemy.future import select
from betternos.models import Server

interval = 5  # seconds

async def update_server_status():
    while True:
        db = SessionLocal()
        try:
            print('Reading servers...')
            servers = await get_servers(db)
            print('Refreshing servers...')
            refreshed_servers = refresh_servers(servers)
            print('Writing servers...')
            for server in refreshed_servers:
                print(f"Server: {server['name']}, IP: {server['ip']}, PID: {server['pid']}")
                result = await db.execute(select(Server).where(Server.name == server['name']))
                server_db = result.scalar_one_or_none()
                server_db.pid = server['pid']
                await db.commit()
                await db.refresh(server_db)
            print('-------------------------------')
        except Exception as e:
            print(f"Error: {e}")
        
        await db.close()
        time.sleep(interval)
        
if __name__ == "__main__":
    asyncio.run(update_server_status())
