# utils/notation_checker.py
# Notation availability checker utilities

import pandas as pd
from data.datasets import IndexFinder

def Notation_Availability_Checker(dfL, n):
    """
    Check if a notation for a specific lyric is available.
    
    Args:
        dfL: DataFrame containing lyric list with 'Lyric no' and 'Status' columns
        n: Lyric number to check
    
    Returns:
        tuple: (notation_name, status) - e.g., ("രാജരാജ ദൈവജാതൻ", "Available")
    """
    try:
        notation_name = IndexFinder(f"L-{n}")
        
        # Check if the status row exists
        status_row = dfL.loc[dfL["Lyric no"] == n, "Status"]
        
        if status_row.empty:
            return (notation_name, "Not Found")
        
        status = status_row.iloc[0]
        return (notation_name, status)
    except Exception as e:
        return ("Error", str(e))


def Get_Missing_Notations(dfL, vocabulary):
    """
    Get all known songs in the lyric vocabulary that need to be uploaded.
    (i.e., where Status != "Available")
    
    Args:
        dfL: DataFrame containing lyric list with 'Lyric no' and 'Status' columns
        vocabulary: Series or DataFrame containing lyric numbers
    
    Returns:
        list: List of tuples [(lyric_num, notation_name), ...] for missing notations
    """
    missing_notations = []
    
    try:
        # Handle both Series and DataFrame inputs
        if isinstance(vocabulary, pd.DataFrame):
            lyric_list = vocabulary["Lyric no"]
        else:
            # It's a Series
            lyric_list = vocabulary
        
        for lyric in lyric_list:
            # Skip empty values
            if pd.isna(lyric) or str(lyric).strip() == '':
                continue
            
            lyric_num = int(lyric)
            status_row = dfL.loc[dfL["Lyric no"] == lyric_num, "Status"]
            
            # Check if status exists and is NOT "Available"
            if not status_row.empty:
                status = status_row.iloc[0]
                if pd.isna(status) or str(status).strip() != "Available":
                    notation_name = IndexFinder(f"L-{int(lyric_num)}")
                    missing_notations.append((lyric_num, notation_name))
            else:
                # Lyric number not found in dfL - add to missing
                notation_name = IndexFinder(f"L-{int(lyric_num)}")
                missing_notations.append((lyric_num, notation_name))
    
    except Exception as e:
        print(f"Error in Get_Missing_Notations: {e}")
        import traceback
        traceback.print_exc()
    
    return missing_notations


def Format_Notation_Availability(notation_name, status):
    """
    Format the notation availability response for Telegram.
    
    Args:
        notation_name: Name/index of the notation
        status: Status of the notation (Available/Pending/etc.)
    
    Returns:
        str: Formatted message for Telegram
    """
    # Create status emoji
    status_emoji = {
        "Available": "✅",
        "Pending": "⏳",
        "Not Found": "❌",
        "Error": "⚠️"
    }.get(status, "❓")
    
    return f"{status_emoji} {notation_name}\n<b>Status:</b> {status}"


def Format_Missing_Notations(missing_notations):
    """
    Format the list of missing notations for Telegram.
    
    Args:
        missing_notations: List of tuples [(lyric_num, notation_name), ...]
    
    Returns:
        str: Formatted message for Telegram
    """
    if not missing_notations:
        return "✅ All known lyrics have their notations available!"
    
    message = f"📋 <b>Missing/Pending Notations</b> ({len(missing_notations)} items):\n\n"
    
    for lyric_num, notation_name in missing_notations:
        message += f"L-{int(lyric_num)}: {notation_name}\n"
    
    return message
