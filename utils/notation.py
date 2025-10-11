# utils/notation.py
# Notation link/image helpers

import re
import pandas as pd
from data.datasets import get_all_data

def getNotation(p):
    try:
        # Handle NaN values and other invalid inputs
        if str(p).lower() in ['nan', 'none', '']:
            return "Page number not available"

        # Clean up the page number - take first part if comma-separated, remove spaces
        page_str = str(p).split(',')[0].strip()
        p = int(page_str)
        if p <= 0:
            return "Enter a valid number"
        elif p < 501:
            return f"https://online.fliphtml5.com/btdsx/ohjz/#p={p}"
        elif p < 838:
            p -= 500
            return f"https://online.fliphtml5.com/btdsx/bszu/#p={p}"
        else:
            return "Invalid Page Number"
    except (ValueError, TypeError):
        return "Page number not available"

def parse_page_list(page_str):
    """
    Parse a comma-separated list of page numbers.
    Returns a list of valid page numbers.
    """
    if not page_str or str(page_str).lower() in ['nan', 'none', '']:
        return []

    pages = []
    for p in str(page_str).split(','):
        p = p.strip()
        if p.isdigit():
            pages.append(int(p))
    return pages

def Music_notation_link(hymnno, dfH, dfTH, Tune_finder_of_known_songs):
    hymnno = str(hymnno).upper().replace('H-', '').replace('H', '').strip()
    results = []
    try:
        hymnno = int(hymnno)
    except Exception:
        return "Invalid Number"
    t = dfH["Tunes"][hymnno - 1]
    t = t.split(',')
    for hymn_name in t:
        hymn_name = hymn_name.strip()
        tune = dfTH[dfTH["Hymn no"] == hymnno]["Tune Index"]
        tune = tune.tolist()
        if hymn_name in tune:
            mask = (dfTH["Hymn no"] == hymnno) & (dfTH["Tune Index"] == hymn_name)
            page_no = dfTH[mask]['Page no']
            if not page_no.empty:
                page = str(page_no.values[0]).split(',')[0]
                # Check for NaN or invalid page numbers
                if page.lower() not in ['nan', 'none', ''] and page.strip().replace('.', '').replace(',', '').replace(' ', '').isdigit():
                    link = getNotation(page)
                    results.append(f'<a href="{link}">{hymn_name}</a>')
                else:
                    results.append(f'{hymn_name}: Page number not available')
            else:
                results.append(f'{hymn_name}: Page not found')
        else:
            for idx, i in enumerate(dfTH['Tune Index']):
                i_list = str(i).split(',')
                if hymn_name in i_list:
                    page_number = str(dfTH['Page no'].iloc[idx]).split(',')[0]
                    # Check for NaN or invalid page numbers
                    if page_number.lower() not in ['nan', 'none', ''] and page_number.strip().replace('.', '').replace(',', '').replace(' ', '').isdigit():
                        link = getNotation(page_number)
                        results.append(f'<a href="{link}">{hymn_name}</a>')
                    else:
                        results.append(f'{hymn_name}: Page number not available')
    if not results:
        return f"{Tune_finder_of_known_songs(f'H-{hymnno}')}: Notation not found"
    return "\n".join(results)

def get_notation_link(page_number):
    """
    Returns a URL for the notation page based on the page number.
    """
    return getNotation(page_number)

def find_tune_page_number(tune_name, hymn_no, dfH, dfTH):
    """
    Enhanced function to find page number for a tune using the new fallback system.

    Priority order:
    1. Check 'Page no' in dfTH for the specific hymn and tune
    2. Check 'Propable_Page_Result' in dfTH for the specific hymn and tune
    3. Check 'Propabible_Pages' in dfH for the hymn and try each page
    4. Check neighboring hymns (±1, ±2, etc.)

    Returns: (page_number, source) or (None, None) if not found
    """
    try:
        hymn_no = int(hymn_no)
        tune_name = tune_name.strip()

        # 1. Check Page no in dfTH first
        page_no = check_tune_in_dfth_page_no(tune_name, hymn_no, dfTH)
        if page_no:
            return page_no, "dfTH_page_no"

        # 2. Check Propable_Page_Result in dfTH
        if 'Propable_Page_Result' in dfTH.columns:
            page_no = check_tune_in_dfth_propable_result(tune_name, hymn_no, dfTH)
            if page_no:
                return page_no, "dfTH_propable_result"

        # 3. Check Propabible_Pages in dfH
        if 'Propabible_Pages' in dfH.columns:
            pages = get_propabible_pages(hymn_no, dfH)
            if pages:
                return pages[0], "dfH_propabible"  # Return first page for now

        # 4. Check neighboring hymns
        for offset in [1, -1, 2, -2, 3, -3, 4, -4, 5, -5]:
            neighbor_hymn = hymn_no + offset
            if neighbor_hymn > 0:  # Ensure positive hymn number
                # Check dfTH Page no for neighbor
                page_no = check_tune_in_dfth_page_no(tune_name, neighbor_hymn, dfTH)
                if page_no:
                    return page_no, f"neighbor_H{neighbor_hymn}_dfTH"

                # Check dfTH Propable_Page_Result for neighbor
                if 'Propable_Page_Result' in dfTH.columns:
                    page_no = check_tune_in_dfth_propable_result(tune_name, neighbor_hymn, dfTH)
                    if page_no:
                        return page_no, f"neighbor_H{neighbor_hymn}_propable"

                # Check dfH Propabible_Pages for neighbor
                if 'Propabible_Pages' in dfH.columns:
                    pages = get_propabible_pages(neighbor_hymn, dfH)
                    if pages:
                        return pages[0], f"neighbor_H{neighbor_hymn}_propabible"

        return None, None

    except Exception as e:
        print(f"Error in find_tune_page_number: {e}")
        return None, None

def check_tune_in_dfth_page_no(tune_name, hymn_no, dfTH):
    """Check if tune exists in dfTH with a valid Page no"""
    if dfTH is None or dfTH.empty:
        return None

    try:
        # Find rows matching hymn number and tune
        import re
        escaped_tune_name = re.escape(tune_name)
        mask = (dfTH["Hymn no"] == hymn_no) & (dfTH["Tune Index"].str.contains(escaped_tune_name, case=False, na=False, regex=True))
        matching_rows = dfTH[mask]

        if not matching_rows.empty:
            page_no = str(matching_rows.iloc[0]["Page no"]).split(',')[0].strip()
            if page_no.lower() not in ['nan', 'none', ''] and page_no.isdigit():
                return int(page_no)
    except Exception:
        pass
    return None

def check_tune_in_dfth_propable_result(tune_name, hymn_no, dfTH):
    """Check if tune exists in dfTH Propable_Page_Result column"""
    if dfTH is None or dfTH.empty or 'Propable_Page_Result' not in dfTH.columns:
        return None

    try:
        # Find rows matching hymn number and tune
        import re
        escaped_tune_name = re.escape(tune_name)
        mask = (dfTH["Hymn no"] == hymn_no) & (dfTH["Tune Index"].str.contains(escaped_tune_name, case=False, na=False, regex=True))
        matching_rows = dfTH[mask]

        if not matching_rows.empty:
            page_no = str(matching_rows.iloc[0]["Propable_Page_Result"]).split(',')[0].strip()
            if page_no.lower() not in ['nan', 'none', ''] and page_no.isdigit():
                return int(page_no)
    except Exception:
        pass
    return None

def get_propabible_pages(hymn_no, dfH):
    """Get Propabible_Pages for a hymn from dfH"""
    if dfH is None or dfH.empty or 'Propabible_Pages' not in dfH.columns:
        return []

    try:
        if hymn_no <= len(dfH):
            page_str = dfH.iloc[hymn_no - 1]['Propabible_Pages']
            return parse_page_list(page_str)
    except Exception:
        pass
    return []

def save_confirmed_page_result(tune_name, hymn_no, page_no, source):
    """
    Save the confirmed page number to appropriate column in dfTH.
    This function would need to update the Google Drive file in a real implementation.
    For now, it just updates the local DataFrame.
    """
    try:
        data = get_all_data()
        dfTH = data["dfTH"]

        if dfTH is None or dfTH.empty:
            return False

        # Ensure columns exist
        if 'Propable_Page_Result' not in dfTH.columns:
            dfTH['Propable_Page_Result'] = ''
        if 'Page no' not in dfTH.columns:
            dfTH['Page no'] = ''

        # Find the row to update
        import re
        escaped_tune_name = re.escape(tune_name)
        mask = (dfTH["Hymn no"] == int(hymn_no)) & (dfTH["Tune Index"].str.contains(escaped_tune_name, case=False, na=False, regex=True))
        matching_indices = dfTH[mask].index

        if not matching_indices.empty:
            # Update based on source priority
            if "dfH_propabible" in str(source):
                # If it came from propabible, update the Propable_Page_Result column
                dfTH.loc[matching_indices[0], 'Propable_Page_Result'] = str(page_no)
                print(f"Saved page {page_no} for tune '{tune_name}' in H-{hymn_no} to Propable_Page_Result")
            else:
                # Otherwise update the Page no column
                dfTH.loc[matching_indices[0], 'Page no'] = str(page_no)
                print(f"Saved page {page_no} for tune '{tune_name}' in H-{hymn_no} to Page no")
            return True
    except Exception as e:
        print(f"Error saving confirmed page result: {e}")
    return False

def save_corrected_page_to_dfth(tune_name, hymn_no, page_no):
    """
    Save user-corrected page number directly to dfTH Page no column.
    This is for when users provide the correct page number after marking one as wrong.
    """
    try:
        data = get_all_data()
        dfTH = data["dfTH"]

        if dfTH is None or dfTH.empty:
            return False

        # Ensure the column exists
        if 'Page no' not in dfTH.columns:
            dfTH['Page no'] = ''

        # Find the row to update
        import re
        escaped_tune_name = re.escape(tune_name)
        mask = (dfTH["Hymn no"] == int(hymn_no)) & (dfTH["Tune Index"].str.contains(escaped_tune_name, case=False, na=False, regex=True))
        matching_indices = dfTH[mask].index

        if not matching_indices.empty:
            # Update the first matching row with the corrected page number
            dfTH.loc[matching_indices[0], 'Page no'] = str(page_no)
            print(f"Corrected page number for '{tune_name}' in H-{hymn_no} to page {page_no}")

            # TODO: Save to Google Drive to persist the change
            # This would require updating the Google Sheets file

            return True
    except Exception as e:
        print(f"Error saving corrected page number: {e}")
    return False