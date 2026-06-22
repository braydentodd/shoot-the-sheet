# Normalization Rules

1. Trim whitespace before and after text completely; in between text, trim whitespace to one space
2. Unicode NFC normalization (e + ́ -> e, etc)
3. Convert diacritics (ß -> ss, é -> e, ñ -> n, ö -> o, etc; we may need a library for this)
4. Normalize apostrophes to ', and hyphens to -
5. if standalone text (meaning if surrounding on both sides by whitespace or start/end of string), normalize 'Saint' to 'St', 'Sainte' to 'Ste', 'Mount' to 'Mt', 'and' to '&', 'LA' to 'Los Angeles'
6. Remove all periods and commas

(May need mapping too... University, University of, College, College of, State, Technical, etc handling...?)