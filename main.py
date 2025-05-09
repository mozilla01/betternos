from fastapi import FastAPI, Header, Response, File, UploadFile, Form, Body
from typing import Annotated
from betternos.models import FileEditRequest
import subprocess
import os
import json
import psutil
import shutil
from betternos.utils import get_servers, download_file, extract_zip
from sqlalchemy.ext.asyncio import AsyncSession
from db import SessionLocal, engine, Base
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        # Create the database tables
        await conn.run_sync(Base.metadata.create_all)
    yield
    
app = FastAPI(lifespan=lifespan)

async def get_db():
    """
    Dependency that provides a database session.
    """
    async with SessionLocal() as session:
        yield session
        
    
@app.get("/{name}/ping")
async def root(name: str, secret: Annotated[str | None, Header()] = None):
    """
    Root endpoint that returns a replies to a ping.
    """
    entry = None
    servers = get_servers()
    for server in servers:
        if server['name'] == name:
            entry = server
            break
    if secret == entry['secret']:
        return {"message": "pong", "name": entry['name'], "ip": entry['ip'], "running": entry['running']}
    else:
        return {"error": "Invalid secret."}
    

@app.post('/{name}/start-server', status_code=200)
async def start_server(name: str, response: Response, secret: Annotated[str | None, Header()] = None):
    """
    Start a server.
    """
    print(f'Starting server {name}')
    print(f'Secret: {secret}')
    servers = get_servers()
    entry = None
    index = None
    for i, server in enumerate(servers):
        if server['name'] == name:
            entry = server
            index = i
            print(f'Found server {server}')
            break
    
    if secret != entry['secret']:
        print(f'Invalid secret {secret}')
        response.status_code = 401
        return {"message": "Invalid secret.", "success": False}
    command = ['java', '-Xmx2G', '-jar', f'{os.path.expanduser("~")}/{name}/{name}.jar', 'nogui']
    
    if entry['running']:
        print(f'Server {name} is already running')
        response.status_code = 400
        return {"message": "Server is already running.", "success": False}
    
    try:
        process = subprocess.Popen(command, start_new_session=True, cwd=f'{os.path.expanduser("~")}/{name}', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        servers[index]['running'] = True
        servers[index]['pid'] = process.pid
        with open(os.path.expanduser('~')+'/servers.json', 'w') as f:
            json.dump(servers, f)
        print(f'Server started with PID {process.pid}')
        print(f'Result written to file')
        response.status_code = 200
        return {"message": "Server started successfully", "success": True}
    except Exception as e:
        response.status_code = 500
        print(f'Error starting server: {e}')
        return {"error": str(e)}
    

@app.post('/{name}/stop-server')
async def stop_server(name: str, secret: Annotated[str | None, Header()] = None):
    """
    Stop a server in a tmux session.
    """
    entry = None
    index = None
    servers = get_servers()
    for i, server in enumerate(servers):
        if server['name'] == name:
            entry = server
            index = i
            break
    if secret != entry['secret']:
        return {"error": "Invalid secret."}
    
    if entry['pid'] is None:
        print(f'Server {name} is already stopped')
        return {"message": "Server is already stopped.", "success": False}
    
    try:
        process = psutil.Process(entry['pid'])
        # Check if the process is running
        if process.is_running():
            # Terminate the process
            process.terminate()
            servers[index]['running'] = False
            servers[index]['pid'] = None
            with open(os.path.expanduser('~')+'/servers.json', 'w') as f:
                json.dump(servers, f)
            return {"message": "Server stopped successfully", "success": True}
        else:
            return {"message": "Process is not running.", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}
    
@app.get('/{name}/get-status')
async def get_logs(name: str, secret: Annotated[str | None, Header()] = None):
    """
    Get logs from latest.log file.
    """
    entry = None
    index = None
    servers = get_servers()
    for i, server in enumerate(servers):
        if server['name'] == name:
            entry = server
            index = i
            break
    if secret != entry['secret']:
        return {"error": "Invalid secret."}
    
    logs = []
    with open(os.path.expanduser('~')+f'/{name}/logs/latest.log', 'r') as f:
        logs = f.readlines()
        
        
    # Get last 100 lines
    logs = logs[-100:]
    return {"logs": logs, "success": True, "running": servers[index]['running']}
    
    
@app.get('/{name}/get-files')
async def get_files(name: str, path: str = None, secret: Annotated[str | None, Header()] = None):
    """
    Get files and folders.
    """
    if path is None:
        path = '/'
    entry = None
    servers = get_servers()
    for server in servers:
        if server['name'] == name:
            entry = server
            break
    if secret != entry['secret']:
        return {"message": "Invalid secret.", "success": False}
    
    path = os.path.expanduser('~')+f'/{name}{path}'
    if os.path.exists(path):
        content = None
        if os.path.isfile(path):
            with open(path, 'r') as f:
                try:
                    content = f.read()
                    print(f'File content: {content}')
                    return {"content": content, "success": True}
                except Exception as e:
                    print(f'Error reading file: {e}')
                    return {"message": "Error reading file.", "success": False}
        elif os.path.isdir(path):
            files = os.listdir(path)
            return {"files": files, "success": True}
        else:
            return {"message": "Path is not a file or folder.", "success": False}
    else:
        return {"message": "Path does not exist.", "success": False}
    
    
@app.post('/{name}/edit-file')
async def edit_file(name: str, request: FileEditRequest, secret: Annotated[str | None, Header()] = None):
    """
    Edit a file.
    """
    print(f'Editing file {request.file_path}')
    entry = None
    servers = get_servers()
    for server in servers:
        if server['name'] == name:
            entry = server
            break
    if secret != entry['secret']:
        return {"message": "Invalid secret.", "success": False}
    
    path = os.path.expanduser('~')+f'/{name}{request.file_path}'
    if os.path.exists(path):
        with open(path, 'w') as f:
            try:
                f.write(request.content)
                return {"message": "File edited successfully", "success": True}
            except Exception as e:
                return {"message": "Error writing to file.", "success": False}
    else:
        return {"message": "Path does not exist.", "success": False}
    
    
@app.post('/{name}/upload-file')
async def upload_file(
        response: Response,
        name: str,
        file_path: Annotated[str | None, Form()] = None,
        file: Annotated[UploadFile | None, File()] = None,
        folder: Annotated[str | None, Form()] = None,
        link: Annotated[str | None, Form()] = None,
        extract: Annotated[bool | None, Form()] = None,
        secret: Annotated[str | None, Header()] = None
    ):
    """
    Upload a file.
    """
    print('Received file upload request')
    print('Data received:')
    print(f'File path: {file_path}')
    print(f'File: {file}')
    print(f'Folder: {folder}')
    print(f'Link: {link}')
    print(f'Extract: {extract}')
    entry = None
    servers = get_servers()
    for server in servers:
        if server['name'] == name:
            entry = server
            break
    if secret != entry['secret']:
        return {"message": "Invalid secret.", "success": False}

    path = file_path
    if path is None:
        path = ''
    path = os.path.expanduser('~')+f'/{name}{path}'
    if folder is not None and folder != '':
        if not os.path.exists(f'{path}/{folder}'):
            os.makedirs(f'{path}/{folder}')
            print(f'Created folder {path}/{folder}')
            return {"message": "Folder created successfully", "success": True, 'data': folder}
        else:
            print(f'Folder {path}/{folder} already exists')
            response.status_code = 400
            return {"message": "Folder already exists.", "success": False}
    if file is not None:
        print(f'File: {file}')
        if extract:
            try:
                extract_zip(file.file, path)
                return {"message": "File extracted successfully", "success": True}
            except Exception as e:
                print(f'Error extracting file: {e}')
                response.status_code = 500
                return {"message": "Error extracting file.", "success": False}
        with open(f'{path}/{file.filename}', 'wb') as f:
            try:
                content = file.file.read()
                filename = file.filename
                f.write(content)
                print(f'File {path} uploaded successfully')
                return {"message": "File uploaded successfully", "success": True, 'data': filename}
            except Exception as e:
                print(f'Error writing file: {e}')
                response.status_code = 500
                return {"message": "Error writing to file.", "success": False}
    elif link is not None and link != '':
        print(f'Link: {link}')
        try:
            filename = download_file(link, path)
            if extract:
                extract_zip(f'{path}/{filename}', path)
                os.remove(f'{path}/{filename}')
                return {"message": "File extracted successfully", "success": True}
            return {"message": "File downloaded successfully", "success": True, 'data': filename}
        except Exception as e:
            print(f'Error downloading file: {e}')
            response.status_code = 500
            return {"message": "Error downloading file.", "success": False}
        
        
@app.post('/{name}/delete-file')
async def delete_file(name: str, request: FileEditRequest, secret: Annotated[str | None, Header()] = None):
    """
    Delete a file.
    """
    entry = None
    servers = get_servers()
    for server in servers:
        if server['name'] == name:
            entry = server
            break
    if secret != entry['secret']:
        return {"message": "Invalid secret.", "success": False}
    file_path = request.file_path
    path = os.path.expanduser('~')+f'/{name}{file_path}'
    if os.path.exists(path):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            return {"message": "File deleted successfully", "success": True, 'data': file_path.split('/')[-1]}
        except Exception as e:
            return {"message": "Error deleting file.", "success": False}
    else:
        return {"message": "Path does not exist.", "success": False}