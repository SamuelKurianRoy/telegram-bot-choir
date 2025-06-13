import re

class Utils:
    @staticmethod
    def standardize_hlc_value(value):
        """Standardizes the HLC value format."""
        value = str(value).upper().strip()

        # Fix format if it's like H 23 or H23 -> H-23
        value = re.sub(r'^([HLC])\s*[-]?\s*(\d+)$', r'\1-\2', value)

        # Replace multiple hyphens with a single hyphen and remove spaces around them
        value = re.sub(r'-+', '-', value)
        value = re.sub(r'\s*-\s*', '-', value)

        return value

    @staticmethod
    def get_notation_link(page_num):
        """Returns the notation link for a given page number."""
        try:
            p = int(str(page_num))
            if p <= 0:
                return "Enter a valid number"
            elif p < 501:
                return f"https://online.fliphtml5.com/btdsx/ohjz/#p={p}"
            elif p < 838:
                p -= 500
                return f"https://online.fliphtml5.com/btdsx/bszu/#p={p}"
            else:
                return "Invalid Page Number"
        except ValueError:
            return "Invalid Page Number"

    def get_music_notation_link(self, hymnno, dfH, dfTH):
        """Returns music notation links for a given hymn number."""
        hymnno = self.standardize_hlc_value(hymnno)
        results = []

        if hymnno.startswith("H"):
            hymnno = hymnno.replace('H', '').strip().replace("-", "")
            hymnno = int(hymnno)
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
                        link = self.get_notation_link(page)
                        results.append(f'<a href="{link}">{hymn_name}</a>')
                    else:
                        results.append(f'{hymn_name}: Page not found')
                else:
                    for idx, i in enumerate(dfTH['Tune Index']):
                        i_list = str(i).split(',')
                        if hymn_name in i_list:
                            page_number = str(dfTH['Page no'].iloc[idx]).split(',')[0]
                            link = self.get_notation_link(page_number)
                            results.append(f'<a href="{link}">{hymn_name}</a>')

            if not results:
                return f"{self.get_tune_for_known_song(f'H-{hymnno}', dfH)}: Notation not found"
            return "\n".join(results)

        else:
            return "Invalid Number"

    @staticmethod
    def get_tune_for_known_song(song, dfH):
        """Returns the tune for a known hymn."""
        song = Utils.standardize_hlc_value(song)
        if song.startswith("H"):
            song = song.replace('H', '').strip().replace("-", "")
            song = int(song)
            return dfH['Tunes'][song-1]
        else:
            return "Invalid Number"
