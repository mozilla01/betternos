import os
import json
import psutil
import requests
import os
from urllib.parse import urlparse
import zipfile
from io import BytesIO
from sqlalchemy import select
from betternos.models import Server


async def get_servers(db):
    """
    Get list of servers from servers.txt file.
    """
    servers = []
    result = await db.execute(select(Server))
    result = result.scalars().all()
    for row in result:
        server = {
            'name': row.name,
            'ip': row.ip,
            'pid': row.pid,
        }
        servers.append(server)
    return servers


def refresh_servers(servers):
    """
    Refresh servers.
    """
    
    for server in servers:
        if server['pid']:
            try:
                process = psutil.Process(server['pid'])
                if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                    print(f"Process {server['pid']} is not running or is a zombie.")
                    server['pid'] = None
            except psutil.NoSuchProcess as e:
                print(f"Process {server['pid']} does not exist: {e}")
                server['pid'] = None
    return servers


def download_file(url, path):

    response = requests.get(url)
    response.raise_for_status()

    # Try to get filename from Content-Disposition header
    cd = response.headers.get('Content-Disposition')
    if cd and 'filename=' in cd:
        filename = cd.split('filename=')[1].strip('\"')
    else:
        # Fallback: use the last part of the URL path
        filename = os.path.basename(urlparse(url).path) or 'downloaded_file'

    # Save the file
    with open(f'{path}/{filename}', 'wb') as file:
        file.write(response.content)

    print(f"Downloaded file as: {filename}")
    
    return filename

def extract_zip(file, path):
    file_data = BytesIO(file.read())
    with zipfile.ZipFile(file_data, 'r') as zip_ref:
        zip_ref.extractall(path)