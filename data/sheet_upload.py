# data/sheet_upload.py
# Handle user sheet music uploads to Google Drive

from googleapiclient.http import MediaFileUpload, MediaIoBaseUpload
from data.drive import get_drive_service
from config import get_config
from logging_utils import setup_loggers
import os
import io
from datetime import datetime

bot_logger, user_logger = setup_loggers()

def upload_file_to_drive(file_path: str, original_filename: str, uploader_name: str, uploader_id: int) -> tuple[bool, str]:
    """
    Upload a file to the Google Drive folder for user contributions.
    
    Args:
        file_path: Local path to the file to upload
        original_filename: Original filename from Telegram
        uploader_name: Name of the user uploading
        uploader_id: Telegram user ID
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        config = get_config()
        drive_service = get_drive_service()
        
        # Get the folder ID from secrets
        folder_id = config.secrets.get("GOOGLE_DRIVE_FOLDER_ID")
        if not folder_id:
            user_logger.error("GOOGLE_DRIVE_FOLDER_ID not found in secrets")
            return False, "Configuration error: Upload folder not set"
        
        # Use the filename as provided by user (already has extension)
        new_filename = original_filename
        
        # Extract extension for MIME type
        _, ext = os.path.splitext(original_filename)
        
        # Prepare file metadata
        file_metadata = {
            'name': new_filename,
            'parents': [folder_id],
            'description': f"Uploaded by {uploader_name} (ID: {uploader_id}) on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        }
        
        # Determine MIME type based on extension
        mime_types = {
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.txt': 'text/plain'
        }
        mime_type = mime_types.get(ext.lower(), 'application/octet-stream')
        
        # Upload the file
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()
        
        file_id = file.get('id')
        file_link = file.get('webViewLink')
        
        user_logger.info(f"✅ File uploaded to Drive: {new_filename} by {uploader_name} (ID: {uploader_id})")
        user_logger.info(f"   Drive file ID: {file_id}")
        
        return True, f"✅ Successfully uploaded!\n\n📁 Filename: `{new_filename}`\n🔗 [View on Drive]({file_link})"
        
    except Exception as e:
        error_msg = str(e)
        user_logger.error(f"❌ Failed to upload file to Drive: {error_msg}")
        
        # Provide helpful message for permission errors
        if "403" in error_msg or "HttpError 403" in error_msg:
            return False, (
                "❌ Upload failed: Permission denied\n\n"
                "⚠️ The service account needs access to the Drive folder.\n"
                "Please share the folder with:\n"
                "`choir-chatbot@angelic-ivy-454609-g3.iam.gserviceaccount.com`\n\n"
                "Give it 'Editor' permissions."
            )
        
        return False, f"❌ Upload failed: {error_msg[:100]}"

def list_uploaded_files(limit: int = 10) -> str:
    """
    List recently uploaded files from the contributions folder.
    
    Args:
        limit: Maximum number of files to list
        
    Returns:
        Formatted string with file list
    """
    try:
        config = get_config()
        drive_service = get_drive_service()
        
        folder_id = config.secrets.get("GOOGLE_DRIVE_FOLDER_ID")
        if not folder_id:
            return "❌ Upload folder not configured"
        
        # Query files in the folder, ordered by creation time
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            pageSize=limit,
            orderBy="createdTime desc",
            fields="files(id, name, createdTime, description, webViewLink)"
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            return "📁 No files uploaded yet."
        
        output = [f"📁 *Recent Uploads* (Last {len(files)}):\n"]
        
        for i, file in enumerate(files, 1):
            name = file.get('name', 'Unknown')
            created = file.get('createdTime', 'Unknown')
            description = file.get('description', '')
            link = file.get('webViewLink', '')
            
            # Parse date
            try:
                date_obj = datetime.fromisoformat(created.replace('Z', '+00:00'))
                date_str = date_obj.strftime('%Y-%m-%d %H:%M')
            except:
                date_str = created
            
            output.append(f"{i}. [{name}]({link})")
            output.append(f"   📅 {date_str}")
            # Description contains uploader info - don't show to users
            output.append("")
        
        return "\n".join(output)
        
    except Exception as e:
        user_logger.error(f"❌ Failed to list uploaded files: {str(e)}")
        return f"❌ Error listing files: {str(e)[:100]}"

def search_uploaded_file_by_lyric(lyric_number: int) -> tuple[bool, str, str]:
    """
    Search for a lyric file in the upload folder by lyric number.
    Looks for filenames containing 'L-XX' pattern.
    
    Args:
        lyric_number: The lyric number to search for (e.g., 32 for L-32)
        
    Returns:
        Tuple of (found: bool, file_id: str, filename: str)
    """
    try:
        config = get_config()
        drive_service = get_drive_service()
        
        folder_id = config.secrets.get("GOOGLE_DRIVE_FOLDER_ID")
        if not folder_id:
            user_logger.error("GOOGLE_DRIVE_FOLDER_ID not found in secrets")
            return False, "", ""
        
        # Search for files containing the lyric pattern
        search_patterns = [
            f"L-{lyric_number}",
            f"L{lyric_number}",
            f"Lyric-{lyric_number}",
            f"Lyric {lyric_number}"
        ]
        
        user_logger.info(f"Searching upload folder for lyric L-{lyric_number}")
        
        # Query all PDF files in the folder
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and trashed=false and mimeType='application/pdf'",
            pageSize=100,
            fields="files(id, name, createdTime)"
        ).execute()
        
        files = results.get('files', [])
        
        # Search for matching files
        for file in files:
            filename = file.get('name', '')
            # Check if any search pattern is in the filename (case-insensitive)
            for pattern in search_patterns:
                if pattern.lower() in filename.lower():
                    user_logger.info(f"✅ Found matching file in uploads: {filename}")
                    return True, file.get('id'), filename
        
        user_logger.info(f"❌ No matching file found in uploads for L-{lyric_number}")
        return False, "", ""
        
    except Exception as e:
        user_logger.error(f"Error searching uploaded files: {str(e)[:100]}")
        return False, "", ""

def download_uploaded_file(file_id: str, filename: str, temp_dir: str) -> str:
    """
    Download a file from the upload folder to a temporary location.
    
    Args:
        file_id: Google Drive file ID
        filename: Original filename
        temp_dir: Temporary directory to save the file
        
    Returns:
        Path to the downloaded file, or None if failed
    """
    try:
        drive_service = get_drive_service()
        
        # Create temp directory if it doesn't exist
        os.makedirs(temp_dir, exist_ok=True)
        
        # Download the file
        from googleapiclient.http import MediaIoBaseDownload
        request = drive_service.files().get_media(fileId=file_id)
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        # Write to temp file
        file_path = os.path.join(temp_dir, filename)
        file_data.seek(0)
        with open(file_path, 'wb') as f:
            f.write(file_data.read())
        
        user_logger.info(f"✅ Downloaded file from uploads: {filename}")
        return file_path
        
    except Exception as e:
        user_logger.error(f"Error downloading uploaded file: {str(e)[:100]}")
        return None


def get_all_uploaded_lyric_numbers() -> set:
    """
    Get all lyric numbers from uploaded files in one API call (FAST).
    Extracts lyric numbers from filenames containing patterns like:
    - L-32, L32, Lyric-32, Lyric 32, lyrics 32
    
    Returns:
        Set of lyric numbers found in uploaded files
    """
    try:
        import re
        config = get_config()
        drive_service = get_drive_service()
        
        folder_id = config.secrets.get("GOOGLE_DRIVE_FOLDER_ID")
        if not folder_id:
            user_logger.error("GOOGLE_DRIVE_FOLDER_ID not found in secrets")
            return set()
        
        # Get all PDF files in ONE API call
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and trashed=false and mimeType='application/pdf'",
            pageSize=1000,  # Get up to 1000 files
            fields="files(id, name)"
        ).execute()
        
        files = results.get('files', [])
        lyric_numbers = set()
        
        # Extract lyric numbers from all filenames
        for file in files:
            filename = file.get('name', '')
            # Look for patterns: L-32, L32, Lyric-32, Lyric 32, lyrics 32
            matches = re.findall(r'(?:L|Lyric|lyrics)[-\s]*(\d+)', filename, re.IGNORECASE)
            for match in matches:
                lyric_numbers.add(int(match))
        
        user_logger.info(f"✅ Found {len(lyric_numbers)} lyric numbers in upload folder (from {len(files)} files)")
        return lyric_numbers
        
    except Exception as e:
        user_logger.error(f"Error getting uploaded lyric numbers: {str(e)}")
        return set()
def search_uploaded_file_by_text(search_text: str) -> list[tuple[str, str]]:
    """
    Search for files in the upload folder by text/keyword.
    Returns all files that contain the search text in their filename.
    
    Args:
        search_text: Text to search for in filenames (e.g., "handel", "advent")
        
    Returns:
        List of tuples: [(file_id, filename), ...]
    """
    try:
        config = get_config()
        drive_service = get_drive_service()
        
        folder_id = config.secrets.get("GOOGLE_DRIVE_FOLDER_ID")
        if not folder_id:
            user_logger.error("GOOGLE_DRIVE_FOLDER_ID not found in secrets")
            return []
        
        search_text_lower = search_text.lower().strip()
        user_logger.info(f"Searching upload folder for text: '{search_text}'")
        
        # Query all PDF files in the folder
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and trashed=false and mimeType='application/pdf'",
            pageSize=100,
            fields="files(id, name, createdTime)"
        ).execute()
        
        files = results.get('files', [])
        matching_files = []
        
        # Search for matching files (case-insensitive)
        for file in files:
            filename = file.get('name', '')
            if search_text_lower in filename.lower():
                matching_files.append((file.get('id'), filename))
        
        if matching_files:
            user_logger.info(f"✅ Found {len(matching_files)} matching file(s) in uploads")
        else:
            user_logger.info(f"❌ No matching files found in uploads for '{search_text}'")
        
        return matching_files
        
    except Exception as e:
        user_logger.error(f"Error searching uploaded files by text: {str(e)[:100]}")
        return []