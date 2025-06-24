# utils/notation.py
# Notation link/image helpers

# TODO: Implement helpers for generating notation links and downloading notation images

import re

def getNotation(p):
    p = int(str(p))
    if p <= 0:
        return "Enter a valid number"
    elif p < 501:
        return f"https://online.fliphtml5.com/btdsx/ohjz/#p={p}"
    elif p < 838:
        p -= 500
        return f"https://online.fliphtml5.com/btdsx/bszu/#p={p}"
    else:
        return "Invalid Page Number"

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
                link = getNotation(page)
                results.append(f'<a href="{link}">{hymn_name}</a>')
            else:
                results.append(f'{hymn_name}: Page not found')
        else:
            for idx, i in enumerate(dfTH['Tune Index']):
                i_list = str(i).split(',')
                if hymn_name in i_list:
                    page_number = str(dfTH['Page no'].iloc[idx]).split(',')[0]
                    link = getNotation(page_number)
                    results.append(f'<a href="{link}">{hymn_name}</a>')
    if not results:
        return f"{Tune_finder_of_known_songs(f'H-{hymnno}')}: Notation not found"
    return "\n".join(results)

def get_notation_link(page_number):
    """
    Returns a URL for the notation page based on the page number.
    """
    # TODO: Implement link generation logic
    return "" 