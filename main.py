from fastapi import FastAPI, Header, Response, File, UploadFile, Form, Depends
from typing import Annotated
from betternos.models import FileEditRequest, Server, CreateServerRequest, ServerConfigRequest
import subprocess
import os
import signal
import psutil
import shutil
from betternos.utils import get_servers, download_file, extract_zip
from sqlalchemy.ext.asyncio import AsyncSession
from betternos.db import SessionLocal, engine, Base
from contextlib import asynccontextmanager
from sqlalchemy.future import select


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
        
        
@app.get("/")
async def read_root(db: AsyncSession = Depends(get_db)):
    """
    Root endpoint that returns a welcome message.
    """
    servers = []
    result = await db.execute(select(Server).where(Server.name == 'server'))
    print(result)
    entry = result.scalar_one_or_none()
    print(entry)
    
    return {"message": "Welcome to the BetterNos API"}
        
    
@app.get("/{name}/ping")
async def root(name: str, db: Annotated[AsyncSession, Depends(get_db)], secret: Annotated[str | None, Header()] = None):
    """
    Root endpoint that returns a replies to a ping.
    """
    entry = await db.execute(select(Server).where(Server.name == name))
    
    entry = entry.scalar_one_or_none()

    if entry is None:
        return {"message": "Server not found.", "success": False}
    if secret == entry.secret:
        return {"message": "pong", "name": entry.name, "ip": entry.ip, "running": entry.pid is not None, "success": True}
    else:
        return {"message": "Invalid secret.", "success": False}
    

@app.post('/{name}/start-server', status_code=200)
async def start_server(name: str, db: Annotated[AsyncSession, Depends(get_db)], response: Response, secret: Annotated[str | None, Header()] = None):
    """
    Start a server.
    """
    print(f'Starting server {name}')
    print(f'Secret: {secret}')

    entry = await db.execute(select(Server).where(Server.name == name))
    entry = entry.scalar_one_or_none()
    if entry is None:
        print(f'Server {name} not found')
        response.status_code = 404
        return {"message": "Server not found.", "success": False}
    
    if secret != entry.secret:
        print(f'Invalid secret {secret}')
        response.status_code = 401
        return {"message": "Invalid secret.", "success": False}
    command = ['java', '-Xmx8G', '-Xms1024M', '-jar', f'{os.path.expanduser("~")}/{name}/{name}.jar', 'nogui']
    if entry.run_cmd:
        command = entry.run_cmd.split(' ')
    
    if entry.pid:
        print(f'Server {name} is already running')
        response.status_code = 400
        return {"message": "Server is already running.", "success": False}
    
    try:
        process = subprocess.Popen(command, start_new_session=True, cwd=f'{os.path.expanduser("~")}/{name}', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        entry.pid = process.pid
        await db.commit()
        await db.refresh(entry)
        print(f'Server started with PID {process.pid}')
        response.status_code = 200
        return {"message": "Server started successfully", "success": True}
    except Exception as e:
        response.status_code = 500
        print(f'Error starting server: {e}')
        return {"error": str(e)}
    

@app.post('/{name}/stop-server')
async def stop_server(name: str, db: Annotated[AsyncSession, Depends(get_db)], secret: Annotated[str | None, Header()] = None):
    """
    Stop a server in a tmux session.
    """
    entry = await db.execute(select(Server).where(Server.name == name))
    entry = entry.scalar_one_or_none()
    if entry is None:
        print(f'Server {name} not found')
        return {"message": "Server not found.", "success": False}

    
    if secret != entry.secret:
        return {"message": "Invalid secret.", "success": False}
    
    if entry.pid is None:
        print(f'Server {name} is already stopped')
        return {"message": "Server is already stopped.", "success": False}
    
    try:
        process = psutil.Process(entry.pid)
        # Check if the process is running
        if process.is_running():
            # Terminate the process
            os.killpg(entry.pid, signal.SIGTERM)
            entry.pid = None
            await db.commit()
            
            return {"message": "Server stopped successfully", "success": True}
        else:
            return {"message": "Process is not running.", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}
    
@app.get('/{name}/get-status')
async def get_logs(name: str, db: Annotated[AsyncSession, Depends(get_db)], secret: Annotated[str | None, Header()] = None):
    """
    Get logs from latest.log file.
    """
    entry = await db.execute(select(Server).where(Server.name == name))
    entry = entry.scalar_one_or_none()
    if entry is None:
        return {"message": "Server not found.", "success": False}
    
    if secret != entry.secret:
        return {"message": "Invalid secret.", "success": False}
    
    command = ['java', '-Xmx8G', '-Xms1024M', '-jar', f'{os.path.expanduser("~")}/{name}/{name}.jar', 'nogui']
    if entry.run_cmd:
        command = entry.run_cmd.split(' ')
    
    logs = []
    try:
        with open(os.path.expanduser('~')+f'/{name}/logs/latest.log', 'r') as f:
            logs = f.readlines()
    except FileNotFoundError as fnf:
        print(f'Error: {fnf}')
        
    # Get last 100 lines
    logs = logs[-100:]
    return {"logs": logs, "success": True, "running": entry.pid is not None, "command": command}
    
    
@app.get('/{name}/get-files')
async def get_files(name: str, db: Annotated[AsyncSession, Depends(get_db)], path: str = None, secret: Annotated[str | None, Header()] = None):
    """
    Get files and folders.
    """
    if path is None:
        path = '/'
    entry = await db.execute(select(Server).where(Server.name == name))
    entry = entry.scalar_one_or_none()
    if entry is None:
        return {"message": "Server not found.", "success": False}
    
    if secret != entry.secret:
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
async def edit_file(name: str, db: Annotated[AsyncSession, Depends(get_db)], request: FileEditRequest, secret: Annotated[str | None, Header()] = None):
    """
    Edit a file.
    """
    print(f'Editing file {request.file_path}')
    entry = await db.execute(select(Server).where(Server.name == name))
    entry = entry.scalar_one_or_none()
    if entry is None:
        return {"message": "Server not found.", "success": False}
    
    if secret != entry.secret:
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
        db: Annotated[AsyncSession, Depends(get_db)],
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
    entry = await db.execute(select(Server).where(Server.name == name))
    entry = entry.scalar_one_or_none()
    if entry is None:
        print(f'Server {name} not found')
        response.status_code = 404
        return {"message": "Server not found.", "success": False}
    
    if secret != entry.secret:
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
async def delete_file(name: str, db: Annotated[AsyncSession, Depends(get_db)], request: FileEditRequest, secret: Annotated[str | None, Header()] = None):
    """
    Delete a file.
    """
    entry = await db.execute(select(Server).where(Server.name == name))
    entry = entry.scalar_one_or_none()
    if entry is None:
        return {"message": "Server not found.", "success": False}
    
    if secret != entry.secret:
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
    
    
@app.post('/create-server')
async def create_server(request: CreateServerRequest, response: Response, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Create a new server.
    """
    name = request.name
    ip = request.ip
    secret = request.secret
    run_cmd = request.run_cmd
    
    print(f'Creating server {name}')
    print(f'Secret: {secret}')
    
    entry = await db.execute(select(Server).where(Server.name == name))
    if entry.scalar_one_or_none() is not None:
        print(f'Server with name "{name}" already exists on this ip.')
        response.status_code = 400
        return {"message": "Server with name \"{name}\" already exists on this ip.", "success": False}
    
    try:
        server = Server(name=name, ip=ip, secret=secret, run_cmd=run_cmd)
        db.add(server)
        await db.commit()
        await db.refresh(server)
        os.mkdir(f'{os.path.expanduser("~")}/{name}')
        print(f'Server {name} created successfully')
        return {"message": "Server created successfully", "success": True}
    except Exception as e:
        print(f'Error creating server: {e}')
        response.status_code = 500
        return {"message": "Error creating server.", "success": False}
    

@app.get('/{name}/delete-server')
async def delete_server(name: str, db: Annotated[AsyncSession, Depends(get_db)], secret: Annotated[str | None, Header()] = None):
    """
    Delete a server.
    """
    entry = await db.execute(select(Server).where(Server.name == name))
    entry = entry.scalar_one_or_none()
    if entry is None:
        return {"message": "Server not found.", "success": False}
    
    if secret != entry.secret:
        return {"message": "Invalid secret.", "success": False}
    
    try:
        shutil.rmtree(f'{os.path.expanduser("~")}/{name}')
        await db.delete(entry)
        await db.commit()
        print(f'Server {name} deleted successfully')
        return {"message": "Server deleted successfully", "success": True}
    except Exception as e:
        print(f'Error deleting server: {e}')
        return {"message": "Error deleting server.", "success": False}
    

@app.post('/{name}/update-run-cmd')
async def update_run_cmd(name: str, request: ServerConfigRequest, db: Annotated[AsyncSession, Depends(get_db)], secret: Annotated[str | None, Header()] = None):
    """
    Update the run command of a server.
    """
    entry = await db.execute(select(Server).where(Server.name == name))
    entry = entry.scalar_one_or_none()
    if entry is None:
        return {"message": "Server not found.", "success": False}
    
    if secret != entry.secret:
        return {"message": "Invalid secret.", "success": False}
    
    try:
        print(f'Updating run command to {request.run_cmd}')
        entry.run_cmd = request.run_cmd
        await db.commit()
        await db.refresh(entry)
        print(f'Run command updated successfully')
        return {"message": "Run command updated successfully", "success": True}
    except Exception as e:
        print(f'Error updating run command: {e}')
        return {"message": "Error updating run command.", "success": False}