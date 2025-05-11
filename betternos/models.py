
from pydantic import BaseModel, Field
from betternos.db import Base
from sqlalchemy import String, Boolean, Integer, Column

class FileEditRequest(BaseModel):
    """
    Model for file edit request.
    """
    file_path: str = Field(..., description="Path to the file to be edited")
    content: str | None = Field(None, description="Content to be written to the file")
    

class CreateServerRequest(BaseModel):
    """
    Model for creating a server.
    """
    name: str = Field(..., description="Name of the server")
    ip: str = Field(..., description="IP address of the server")
    secret: str = Field(..., description="Secret key for the server")
    run_cmd: str | None = Field(None, description="Command to run the server")
    
class ServerConfigRequest(BaseModel):
    """
    Model for server configuration.
    """
    run_cmd: str | None = Field(None, description="Command to run the server")
    
    
# Database models

class Server(Base):
    """
    Model for servers
    """
    
    __tablename__ = "servers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False, unique=True)
    ip = Column(String, nullable=False)
    pid = Column(Integer)
    secret = Column(String, nullable=False)
    run_cmd = Column(String, nullable=True)