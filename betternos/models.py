
from pydantic import BaseModel, Field
from db import Base
from sqlalchemy import String, Boolean, Integer, Column

class FileEditRequest(BaseModel):
    """
    Model for file edit request.
    """
    file_path: str = Field(..., description="Path to the file to be edited")
    content: str | None = Field(None, description="Content to be written to the file")
    
    
# Database models

class Server(Base):
    """
    Model for servers
    """
    
    __tablename__ = "servers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    ip = Column(String, nullable=False)
    pid = Column(Integer)