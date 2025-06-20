import os
import re
import requests


def extract_folder_id(folder_url):
    """
    Extracts the folder ID from a Google Drive folder URL.
    """
    match = re.search(r'/folders/([a-zA-Z0-9_-]+)', folder_url)
    if match:
        return match.group(1)
    raise ValueError("Invalid folder URL")


def get_image_files_from_folder(drive_service, folder_url):
    """
    Fetches all image files from a Google Drive folder and returns a map of page number to file ID.
    """
    folder_id = extract_folder_id(folder_url)
    file_map = {}
    page_token = None
    while True:
        response = drive_service.files().list(
            q=f"'{folder_id}' in parents and mimeType contains 'image/' and trashed = false",
            fields="nextPageToken, files(id, name)",
            pageToken=page_token
        ).execute()
        for file in response.get('files', []):
            try:
                page_num = int(file['name'].split('.')[0])
                file_map[page_num] = file['id']
            except ValueError:
                continue  # Skip files that don't start with a number
        page_token = response.get('nextPageToken', None)
        if page_token is None:
            break
    return file_map


def download_image(file_id, filename, download_dir):
    """
    Downloads an image from Google Drive by file ID and saves it to the specified directory.
    """
    url = f"https://drive.google.com/uc?id={file_id}"
    response = requests.get(url)
    if response.status_code == 200:
        file_path = os.path.join(download_dir, filename)
        with open(file_path, 'wb') as f:
            f.write(response.content)
        return file_path
    else:
        return None


def get_image_by_page(page_number, file_map, download_dir):
    """
    Gets the image file for a given page number using the file map and downloads it if necessary.
    """
    page_number = int(page_number)
    if page_number in file_map:
        file_id = file_map[page_number]
        filename = f"{page_number}.jpg"
        return download_image(file_id, filename, download_dir)
    else:
        return None 