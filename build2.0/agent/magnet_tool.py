# /home/ubuntu/chatbot_project/tools/magnet_tool.py
"""
Tool for fetching metadata from a torrent magnet link and optionally downloading content.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# --- Pydantic Schemas for Input and Output ---

class MagnetLinkInput(BaseModel):
    """Input schema for providing a magnet link."""
    magnet_link: str = Field(..., description="The torrent magnet URI.")

class TorrentFileMetadata(BaseModel):
    """Schema for metadata of a single file within a torrent."""
    path: str
    size: int # Size in bytes

class MagnetMetadataOutput(BaseModel):
    """Output schema after fetching metadata from a magnet link."""
    torrent_name: Optional[str] = None
    total_size: Optional[int] = None # Total size of all files in bytes
    num_files: Optional[int] = None
    files: Optional[List[TorrentFileMetadata]] = []
    info_hash: Optional[str] = None
    error: Optional[str] = None

class MagnetDownloadInput(BaseModel):
    """Input schema to confirm and initiate download of a torrent."""
    magnet_link: str = Field(..., description="The torrent magnet URI to download.")
    # Potentially add specific files to download if library supports partial downloads
    # target_directory: Optional[str] = None # Could be specified or use a default from config

class MagnetDownloadStatusOutput(BaseModel):
    """Output schema for the status of a torrent download."""
    status: str # e.g., "downloading", "completed", "failed", "stalled", "checking_files"
    progress: float = Field(0.0, description="Download progress as a percentage (0.0 to 100.0)")
    download_speed: float = Field(0.0, description="Download speed in bytes/sec")
    upload_speed: float = Field(0.0, description="Upload speed in bytes/sec")
    num_peers: Optional[int] = None
    num_seeds: Optional[int] = None
    download_path: Optional[str] = None # Path where content is being/was downloaded
    error: Optional[str] = None
    message: Optional[str] = None # e.g., "Metadata successfully fetched, awaiting download confirmation."

# --- General Input to select the type of Magnet action ---
class MagnetActionInput(BaseModel):
    action: str = Field(..., description="Action to perform: get_metadata, download_torrent, check_download_status")
    parameters: Dict[str, Any]

# --- Placeholder for Core Tool Logic & Langchain Integration --- 
# Actual implementation will use libtorrentrasterbar or similar.
# This will be filled in during the implementation step for this tool.

