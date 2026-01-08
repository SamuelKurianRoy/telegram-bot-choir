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
        
        # Create a descriptive filename with timestamp and uploader info
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Clean the original filename
        name, ext = os.path.splitext(original_filename)
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
        new_filename = f"{timestamp}_{safe_name}_by_{uploader_name}{ext}"
        
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
        user_logger.error(f"❌ Failed to upload file to Drive: {str(e)}")
        return False, f"❌ Upload failed: {str(e)[:100]}"

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
            if description:
                output.append(f"   ℹ️ {description}")
            output.append("")
        
        return "\n".join(output)
        
    except Exception as e:
        user_logger.error(f"❌ Failed to list uploaded files: {str(e)}")
        return f"❌ Error listing files: {str(e)[:100]}"
