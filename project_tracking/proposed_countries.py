"""
Shoot the Sheet - Country Registry

Canonical country metadata for international sporting affiliations (FIFA, FIBA, IIHF, WBC, IFAF).
"""

from typing import TypedDict


class Country(TypedDict):
    name: str
    aliases: list[str]


COUNTRIES: dict[str, Country] = {
    "AFG": {
        "name": "Afghanistan",
        "aliases": ["AFG", "Afghanistan", "Islamic Republic of Afghanistan", "Afganistan"],
    },
    "AHO": {
        "name": "Netherlands Antilles",
        "aliases": ["AHO", "ANT", "Netherlands Antilles", "Dutch Antilles"],
    },
    "AIA": {
        "name": "Anguilla",
        "aliases": ["AIA", "Anguilla"],
    },
    "ALB": {
        "name": "Albania",
        "aliases": ["ALB", "Albania", "Republic of Albania", "Shqiperia", "Shqiperi"],
    },
    "ALG": {
        "name": "Algeria",
        "aliases": ["ALG", "DZA", "Algeria", "People's Democratic Republic of Algeria", "Al Jazair"],
    },
    "AND": {
        "name": "Andorra",
        "aliases": ["AND", "Andorra", "Principality of Andorra"],
    },
    "ANG": {
        "name": "Angola",
        "aliases": ["ANG", "AGO", "Angola", "Republic of Angola"],
    },
    "ANT": {
        "name": "Antigua & Barbuda",
        "aliases": ["ANT", "ATG", "Antigua & Barbuda", "Antigua", "Barbuda"],
    },
    "ARG": {
        "name": "Argentina",
        "aliases": ["ARG", "Argentina", "Argentine Republic"],
    },
    "ARM": {
        "name": "Armenia",
        "aliases": ["ARM", "Armenia", "Republic of Armenia", "Hayastan"],
    },
    "ARU": {
        "name": "Aruba",
        "aliases": ["ARU", "ABW", "Aruba"],
    },
    "ASA": {
        "name": "American Samoa",
        "aliases": ["ASA", "ASM", "American Samoa"],
    },
    "AUS": {
        "name": "Australia",
        "aliases": ["AUS", "Australia", "Commonwealth of Australia"],
    },
    "AUT": {
        "name": "Austria",
        "aliases": ["AUT", "Austria", "Republic of Austria", "Oesterreich", "Osterreich"],
    },
    "AZE": {
        "name": "Azerbaijan",
        "aliases": ["AZE", "Azerbaijan", "Republic of Azerbaijan", "AZ", "Azerbaycan"],
    },
    "BAH": {
        "name": "Bahamas",
        "aliases": ["BAH", "BHS", "Bahamas", "Commonwealth of the Bahamas", "The Bahamas"],
    },
    "BAN": {
        "name": "Bangladesh",
        "aliases": ["BAN", "BGD", "Bangladesh", "People's Republic of Bangladesh"],
    },
    "BAR": {
        "name": "Barbados",
        "aliases": ["BAR", "BRB", "Barbados"],
    },
    "BDI": {
        "name": "Burundi",
        "aliases": ["BDI", "Burundi", "Republic of Burundi"],
    },
    "BEL": {
        "name": "Belgium",
        "aliases": ["BEL", "Belgium", "Kingdom of Belgium", "BE", "Belgie"],
    },
    "BEN": {
        "name": "Benin",
        "aliases": ["BEN", "Benin", "Republic of Benin", "Dahomey"],
    },
    "BER": {
        "name": "Bermuda",
        "aliases": ["BER", "BMU", "Bermuda", "The Islands of Bermuda", "Bermudas"],
    },
    "BHU": {
        "name": "Bhutan",
        "aliases": ["BHU", "BTN", "Bhutan", "Kingdom of Bhutan", "Druk Yul"],
    },
    "BIH": {
        "name": "Bosnia & Herzegovina",
        "aliases": ["BIH", "Bosnia & Herzegovina", "Bosnia-Herzegovina", "Bosnia", "Herzegovina"],
    },
    "BIZ": {
        "name": "Belize",
        "aliases": ["BIZ", "BLZ", "Belize"],
    },
    "BLR": {
        "name": "Belarus",
        "aliases": ["BLR", "Belarus", "Republic of Belarus", "Byelorussia"],
    },
    "BOL": {
        "name": "Bolivia",
        "aliases": ["BOL", "Bolivia", "Plurinational State of Bolivia"],
    },
    "BON": {
        "name": "Bonaire",
        "aliases": ["BON", "BOE", "BES", "Bonaire", "Caribbean Netherlands", "Sint Eustatius", "Saba"],
    },
    "BOT": {
        "name": "Botswana",
        "aliases": ["BOT", "BWA", "Botswana", "Republic of Botswana", "Bechuanaland"],
    },
    "BRA": {
        "name": "Brazil",
        "aliases": ["BRA", "Brazil", "Federative Republic of Brazil", "BR"],
    },
    "BRN": {
        "name": "Bahrain",
        "aliases": ["BRN", "BHR", "Bahrain", "Kingdom of Bahrain"],
    },
    "BRU": {
        "name": "Brunei",
        "aliases": ["BRU", "Brunei", "Brunei Darussalam"],
    },
    "BUL": {
        "name": "Bulgaria",
        "aliases": ["BUL", "BGR", "Bulgaria", "Republic of Bulgaria"],
    },
    "BUR": {
        "name": "Burkina Faso",
        "aliases": ["BUR", "BFA", "Burkina Faso", "BF", "Burkina", "Upper Volta"],
    },
    "CAF": {
        "name": "Central African Republic",
        "aliases": ["CAF", "CAR", "Central African Republic"],
    },
    "CAM": {
        "name": "Cambodia",
        "aliases": ["CAM", "KHM", "Cambodia", "Kingdom of Cambodia"],
    },
    "CAN": {
        "name": "Canada",
        "aliases": ["CAN", "Canada", "CA"],
    },
    "CAY": {
        "name": "Cayman Islands",
        "aliases": ["CAY", "CYM", "Cayman Islands", "Cayman"],
    },
    "CGO": {
        "name": "Republic of the Congo",
        "aliases": ["CGO", "COG", "Congo", "Republic of the Congo", "Congo Brazzaville"],
    },
    "CHA": {
        "name": "Chad",
        "aliases": ["CHA", "TCD", "Chad", "Republic of Chad"],
    },
    "CHI": {
        "name": "Chile",
        "aliases": ["CHI", "CHL", "Chile", "Republic of Chile"],
    },
    "CHN": {
        "name": "China",
        "aliases": ["CHN", "China", "People's Republic of China", "Zhongguo", "PR China"],
    },
    "CIV": {
        "name": "Ivory Coast",
        "aliases": ["CIV", "Ivory Coast", "Republic of Cote d'Ivoire", "Cote d'Ivoire", "Cote dIvoire"],
    },
    "CMR": {
        "name": "Cameroon",
        "aliases": ["CMR", "Cameroon", "Republic of Cameroon"],
    },
    "COD": {
        "name": "Democratic Republic of the Congo",
        "aliases": ["COD", "DR Congo", "Congo DR", "Democratic Republic of the Congo", "DRC", "Zaire", "Congo Kinshasa"],
    },
    "COK": {
        "name": "Cook Islands",
        "aliases": ["COK", "Cook Islands"],
    },
    "COL": {
        "name": "Colombia",
        "aliases": ["COL", "Colombia", "Republic of Colombia"],
    },
    "COM": {
        "name": "Comoros",
        "aliases": ["COM", "Comoros", "Union of the Comoros"],
    },
    "CPV": {
        "name": "Cape Verde",
        "aliases": ["CPV", "Cape Verde", "Republic of Cabo Verde", "Cabo Verde", "CV", "CVD"],
    },
    "CRC": {
        "name": "Costa Rica",
        "aliases": ["CRC", "CRI", "Costa Rica", "Republic of Costa Rica", "CR"],
    },
    "CRO": {
        "name": "Croatia",
        "aliases": ["CRO", "HRV", "Croatia", "Republic of Croatia", "Hrvatska"],
    },
    "CUB": {
        "name": "Cuba",
        "aliases": ["CUB", "Cuba", "Republic of Cuba"],
    },
    "CUW": {
        "name": "Curaçao",
        "aliases": ["CUW", "Curacao", "Curaçao", "Country of Curacao"],
    },
    "CYP": {
        "name": "Cyprus",
        "aliases": ["CYP", "Cyprus", "Republic of Cyprus"],
    },
    "CZE": {
        "name": "Czech Republic",
        "aliases": ["CZE", "Czechia", "Czech Republic", "Czech", "Cesko"],
    },
    "DEN": {
        "name": "Denmark",
        "aliases": ["DEN", "DNK", "Denmark", "Kingdom of Denmark", "Danmark"],
    },
    "DJI": {
        "name": "Djibouti",
        "aliases": ["DJI", "Djibouti", "Republic of Djibouti"],
    },
    "DMA": {
        "name": "Dominica",
        "aliases": ["DMA", "Dominica", "Commonwealth of Dominica"],
    },
    "DOM": {
        "name": "Dominican Republic",
        "aliases": ["DOM", "Dominican Republic"],
    },
    "ECU": {
        "name": "Ecuador",
        "aliases": ["ECU", "Ecuador", "Republic of Ecuador"],
    },
    "EGY": {
        "name": "Egypt",
        "aliases": ["EGY", "Egypt", "Arab Republic of Egypt", "Misr"],
    },
    "ENG": {
        "name": "England",
        "aliases": ["ENG", "England"],
    },
    "ERI": {
        "name": "Eritrea",
        "aliases": ["ERI", "Eritrea", "State of Eritrea"],
    },
    "ESA": {
        "name": "El Salvador",
        "aliases": ["ESA", "SLV", "El Salvador", "Republic of El Salvador"],
    },
    "ESP": {
        "name": "Spain",
        "aliases": ["ESP", "Spain", "Kingdom of Spain", "Espana"],
    },
    "EST": {
        "name": "Estonia",
        "aliases": ["EST", "Estonia", "Republic of Estonia", "Eesti"],
    },
    "ETH": {
        "name": "Ethiopia",
        "aliases": ["ETH", "Ethiopia", "Federal Democratic Republic of Ethiopia"],
    },
    "FIJ": {
        "name": "Fiji",
        "aliases": ["FIJ", "FJI", "Fiji", "Republic of Fiji", "Viti"],
    },
    "FIN": {
        "name": "Finland",
        "aliases": ["FIN", "Finland", "Republic of Finland", "Suomi"],
    },
    "FLK": {
        "name": "Falkland Islands",
        "aliases": ["FLK", "FK", "Falkland Islands"],
    },
    "FRA": {
        "name": "France",
        "aliases": ["FRA", "France", "French Republic", "FR"],
    },
    "FRO": {
        "name": "Faroe Islands",
        "aliases": ["FRO", "Faroe Islands", "Foroyar"],
    },
    "FSM": {
        "name": "Micronesia",
        "aliases": ["FSM", "Micronesia", "Federated States of Micronesia"],
    },
    "GAB": {
        "name": "Gabon",
        "aliases": ["GAB", "Gabon", "Gabonese Republic"],
    },
    "GAM": {
        "name": "Gambia",
        "aliases": ["GAM", "GMB", "Gambia", "Republic of the Gambia", "The Gambia"],
    },
    "GBR": {
        "name": "Great Britain",
        "aliases": ["GBR", "United Kingdom", "United Kingdom of Great Britain & Northern Ireland", "GB", "UK", "Great Britain", "Britain"],
    },
    "GBS": {
        "name": "Guinea-Bissau",
        "aliases": ["GBS", "GNB", "Guinea-Bissau", "Republic of Guinea-Bissau"],
    },
    "GEO": {
        "name": "Georgia",
        "aliases": ["GEO", "Georgia", "Sakartvelo"],
    },
    "GEQ": {
        "name": "Equatorial Guinea",
        "aliases": ["GEQ", "GNQ", "Equatorial Guinea", "Republic of Equatorial Guinea"],
    },
    "GER": {
        "name": "Germany",
        "aliases": ["GER", "DEU", "Germany", "Federal Republic of Germany", "Deutschland", "West Germany", "East Germany", "FRG", "GDR"],
    },
    "GGY": {
        "name": "Guernsey",
        "aliases": ["GGY", "Guernsey", "Bailiwick of Guernsey"],
    },
    "GHA": {
        "name": "Ghana",
        "aliases": ["GHA", "Ghana", "Republic of Ghana", "Gold Coast"],
    },
    "GIB": {
        "name": "Gibraltar",
        "aliases": ["GIB", "Gibraltar"],
    },
    "GLP": {
        "name": "Guadeloupe",
        "aliases": ["GLP", "Guadeloupe"],
    },
    "GRE": {
        "name": "Greece",
        "aliases": ["GRE", "GRC", "Greece", "Hellenic Republic", "Hellas"],
    },
    "GRL": {
        "name": "Greenland",
        "aliases": ["GRL", "Greenland", "Kalaallit Nunaat"],
    },
    "GRN": {
        "name": "Grenada",
        "aliases": ["GRN", "GRD", "Grenada"],
    },
    "GUA": {
        "name": "Guatemala",
        "aliases": ["GUA", "GTM", "Guatemala", "Republic of Guatemala"],
    },
    "GUF": {
        "name": "French Guiana",
        "aliases": ["GUF", "French Guiana", "Guiana"],
    },
    "GUI": {
        "name": "Guinea",
        "aliases": ["GUI", "GIN", "Guinea", "Republic of Guinea"],
    },
    "GUM": {
        "name": "Guam",
        "aliases": ["GUM", "Guam"],
    },
    "GUY": {
        "name": "Guyana",
        "aliases": ["GUY", "Guyana", "Co-operative Republic of Guyana"],
    },
    "HAI": {
        "name": "Haiti",
        "aliases": ["HAI", "HTI", "Haiti", "Republic of Haiti"],
    },
    "HKG": {
        "name": "Hong Kong",
        "aliases": ["HKG", "Hong Kong", "HK", "Hong Kong China"],
    },
    "HON": {
        "name": "Honduras",
        "aliases": ["HON", "HND", "Honduras", "Republic of Honduras"],
    },
    "HUN": {
        "name": "Hungary",
        "aliases": ["HUN", "Hungary", "Magyarorszag"],
    },
    "IMN": {
        "name": "Isle of Man",
        "aliases": ["IMN", "Isle of Man"],
    },
    "INA": {
        "name": "Indonesia",
        "aliases": ["INA", "IDN", "Indonesia", "Republic of Indonesia"],
    },
    "IND": {
        "name": "India",
        "aliases": ["IND", "India", "Republic of India", "Bharat"],
    },
    "IRI": {
        "name": "Iran",
        "aliases": ["IRI", "IRN", "Iran", "Islamic Republic of Iran", "Persia", "IR Iran"],
    },
    "IRL": {
        "name": "Ireland",
        "aliases": ["IRL", "Ireland", "Republic of Ireland", "Eire"],
    },
    "IRQ": {
        "name": "Iraq",
        "aliases": ["IRQ", "Iraq", "Republic of Iraq", "IQ"],
    },
    "ISL": {
        "name": "Iceland",
        "aliases": ["ISL", "Iceland", "Republic of Iceland", "Island"],
    },
    "ISR": {
        "name": "Israel",
        "aliases": ["ISR", "Israel", "State of Israel"],
    },
    "ISV": {
        "name": "United States Virgin Islands",
        "aliases": ["ISV", "VIR", "United States Virgin Islands", "Virgin Islands US", "US Virgin Islands"],
    },
    "ITA": {
        "name": "Italy",
        "aliases": ["ITA", "Italy", "Italian Republic", "Italia"],
    },
    "IVB": {
        "name": "British Virgin Islands",
        "aliases": ["IVB", "VGB", "British Virgin Islands", "Virgin Islands British"],
    },
    "JAM": {
        "name": "Jamaica",
        "aliases": ["JAM", "Jamaica", "JM"],
    },
    "JEY": {
        "name": "Jersey",
        "aliases": ["JEY", "Jersey", "Bailiwick of Jersey"],
    },
    "JOR": {
        "name": "Jordan",
        "aliases": ["JOR", "Jordan", "Hashemite Kingdom of Jordan", "Al Urdun"],
    },
    "JPN": {
        "name": "Japan",
        "aliases": ["JPN", "Japan", "Nippon", "Nihon"],
    },
    "KAZ": {
        "name": "Kazakhstan",
        "aliases": ["KAZ", "Kazakhstan", "Republic of Kazakhstan", "Qazaqstan"],
    },
    "KEN": {
        "name": "Kenya",
        "aliases": ["KEN", "Kenya", "Republic of Kenya", "KE"],
    },
    "KGZ": {
        "name": "Kyrgyzstan",
        "aliases": ["KGZ", "Kyrgyzstan", "Kyrgyz Republic", "KG"],
    },
    "KIR": {
        "name": "Kiribati",
        "aliases": ["KIR", "Kiribati", "Republic of Kiribati", "KI"],
    },
    "KOR": {
        "name": "South Korea",
        "aliases": ["KOR", "South Korea", "Republic of Korea", "Korea", "Hanguk", "Korea Rep"],
    },
    "KOS": {
        "name": "Kosovo",
        "aliases": ["KOS", "UNK", "Kosovo", "Republic of Kosovo", "Kosova"],
    },
    "KSA": {
        "name": "Saudi Arabia",
        "aliases": ["KSA", "SAU", "Saudi Arabia", "Kingdom of Saudi Arabia", "Saudi", "SA"],
    },
    "KUW": {
        "name": "Kuwait",
        "aliases": ["KUW", "KWT", "Kuwait", "State of Kuwait", "KW"],
    },
    "LAO": {
        "name": "Laos",
        "aliases": ["LAO", "Laos", "Lao People's Democratic Republic"],
    },
    "LAT": {
        "name": "Latvia",
        "aliases": ["LAT", "LVA", "Latvia", "Republic of Latvia", "Latvija"],
    },
    "LBA": {
        "name": "Libya",
        "aliases": ["LBA", "LBY", "Libya", "State of Libya"],
    },
    "LBN": {
        "name": "Lebanon",
        "aliases": ["LBN", "Lebanon", "Lebanese Republic", "Lubnan"],
    },
    "LBR": {
        "name": "Liberia",
        "aliases": ["LBR", "Liberia", "Republic of Liberia"],
    },
    "LCA": {
        "name": "St Lucia",
        "aliases": ["LCA", "St. Lucia", "Lucia"],
    },
    "LES": {
        "name": "Lesotho",
        "aliases": ["LES", "LSO", "Lesotho", "Kingdom of Lesotho"],
    },
    "LIE": {
        "name": "Liechtenstein",
        "aliases": ["LIE", "Liechtenstein", "Principality of Liechtenstein"],
    },
    "LTU": {
        "name": "Lithuania",
        "aliases": ["LTU", "Lithuania", "Republic of Lithuania", "Lietuva"],
    },
    "LUX": {
        "name": "Luxembourg",
        "aliases": ["LUX", "Luxembourg", "Grand Duchy of Luxembourg"],
    },
    "MAC": {
        "name": "Macau",
        "aliases": ["MAC", "Macau", "Macao", "Macao China", "Macau China"],
    },
    "MAD": {
        "name": "Madagascar",
        "aliases": ["MAD", "MDG", "Madagascar", "Republic of Madagascar"],
    },
    "MAF": {
        "name": "Saint Martin",
        "aliases": ["MAF", "St. Martin", "Saint Martin", "Collectivity of St. Martin"],
    },
    "MAR": {
        "name": "Morocco",
        "aliases": ["MAR", "Morocco", "Kingdom of Morocco", "Al Maghrib"],
    },
    "MAS": {
        "name": "Malaysia",
        "aliases": ["MAS", "MYS", "Malaysia"],
    },
    "MAT": {
        "name": "Montserrat",
        "aliases": ["MAT", "MSR", "Montserrat"],
    },
    "MAW": {
        "name": "Malawi",
        "aliases": ["MAW", "MWI", "Malawi", "Republic of Malawi"],
    },
    "MDA": {
        "name": "Moldova",
        "aliases": ["MDA", "Moldova", "Republic of Moldova"],
    },
    "MDV": {
        "name": "Maldives",
        "aliases": ["MDV", "Maldives", "Republic of the Maldives"],
    },
    "MEX": {
        "name": "Mexico",
        "aliases": ["MEX", "Mexico", "United Mexican States", "MX"],
    },
    "MGL": {
        "name": "Mongolia",
        "aliases": ["MGL", "MNG", "Mongolia", "Mongol Uls"],
    },
    "MHL": {
        "name": "Marshall Islands",
        "aliases": ["MHL", "Marshall Islands", "Republic of the Marshall Islands"],
    },
    "MKD": {
        "name": "North Macedonia",
        "aliases": ["MKD", "North Macedonia", "Republic of North Macedonia", "Macedonia", "FYROM"],
    },
    "MLI": {
        "name": "Mali",
        "aliases": ["MLI", "Mali", "Republic of Mali"],
    },
    "MLT": {
        "name": "Malta",
        "aliases": ["MLT", "Malta", "Republic of Malta"],
    },
    "MNE": {
        "name": "Montenegro",
        "aliases": ["MNE", "Montenegro", "Crna Gora"],
    },
    "MON": {
        "name": "Monaco",
        "aliases": ["MON", "MCO", "Monaco", "Principality of Monaco"],
    },
    "MOZ": {
        "name": "Mozambique",
        "aliases": ["MOZ", "Mozambique", "Republic of Mozambique"],
    },
    "MRI": {
        "name": "Mauritius",
        "aliases": ["MRI", "MUS", "Mauritius", "Republic of Mauritius"],
    },
    "MTN": {
        "name": "Mauritania",
        "aliases": ["MTN", "MRT", "Mauritania", "Islamic Republic of Mauritania"],
    },
    "MTQ": {
        "name": "Martinique",
        "aliases": ["MTQ", "Martinique"],
    },
    "MYA": {
        "name": "Myanmar",
        "aliases": ["MYA", "MMR", "Myanmar", "Burma"],
    },
    "MYT": {
        "name": "Mayotte",
        "aliases": ["MYT", "Mayotte"],
    },
    "NAM": {
        "name": "Namibia",
        "aliases": ["NAM", "Namibia", "Republic of Namibia", "South West Africa"],
    },
    "NCA": {
        "name": "Nicaragua",
        "aliases": ["NCA", "NIC", "Nicaragua", "Republic of Nicaragua"],
    },
    "NCL": {
        "name": "New Caledonia",
        "aliases": ["NCL", "CAL", "New Caledonia", "Caledonia"],
    },
    "NED": {
        "name": "Netherlands",
        "aliases": ["NED", "NLD", "Netherlands", "Kingdom of the Netherlands", "Holland", "Nederland"],
    },
    "NEP": {
        "name": "Nepal",
        "aliases": ["NEP", "NPL", "Nepal", "Federal Democratic Republic of Nepal"],
    },
    "NGR": {
        "name": "Nigeria",
        "aliases": ["NGR", "NGA", "Nigeria", "Federal Republic of Nigeria"],
    },
    "NIG": {
        "name": "Niger",
        "aliases": ["NIG", "NER", "Niger", "Republic of Niger"],
    },
    "NIR": {
        "name": "Northern Ireland",
        "aliases": ["NIR", "Northern Ireland"],
    },
    "NIU": {
        "name": "Niue",
        "aliases": ["NIU", "Niue"],
    },
    "NMI": {
        "name": "Northern Mariana Islands",
        "aliases": ["NMI", "MNP", "Northern Mariana Islands"],
    },
    "NOR": {
        "name": "Norway",
        "aliases": ["NOR", "Norway", "Kingdom of Norway", "NO", "Norge"],
    },
    "NRU": {
        "name": "Naoero",
        "aliases": ["NRU", "Nauru", "Naoero", "Republic of Nauru"],
    },
    "NZL": {
        "name": "New Zealand",
        "aliases": ["NZL", "New Zealand", "NZ", "Aotearoa"],
    },
    "OMA": {
        "name": "Oman",
        "aliases": ["OMA", "OMN", "Oman", "Sultanate of Oman"],
    },
    "PAK": {
        "name": "Pakistan",
        "aliases": ["PAK", "Pakistan", "Islamic Republic of Pakistan"],
    },
    "PAN": {
        "name": "Panama",
        "aliases": ["PAN", "Panama", "Republic of Panama"],
    },
    "PAR": {
        "name": "Paraguay",
        "aliases": ["PAR", "PRY", "Paraguay", "Republic of Paraguay"],
    },
    "PER": {
        "name": "Peru",
        "aliases": ["PER", "Peru", "Republic of Peru"],
    },
    "PHI": {
        "name": "Philippines",
        "aliases": ["PHI", "PHL", "Philippines", "Republic of the Philippines"],
    },
    "PLE": {
        "name": "Palestine",
        "aliases": ["PLE", "PSE", "Palestine", "State of Palestine"],
    },
    "PLW": {
        "name": "Palau",
        "aliases": ["PLW", "Palau", "Republic of Palau"],
    },
    "PNG": {
        "name": "Papua New Guinea",
        "aliases": ["PNG", "Papua New Guinea"],
    },
    "POL": {
        "name": "Poland",
        "aliases": ["POL", "Poland", "Republic of Poland", "Polska"],
    },
    "POR": {
        "name": "Portugal",
        "aliases": ["POR", "PRT", "Portugal", "Portuguese Republic"],
    },
    "PRK": {
        "name": "North Korea",
        "aliases": ["PRK", "North Korea", "Democratic People's Republic of Korea", "DPRK", "Korea DPR"],
    },
    "PUR": {
        "name": "Puerto Rico",
        "aliases": ["PUR", "PRI", "Puerto Rico", "Commonwealth of Puerto Rico", "PR"],
    },
    "QAT": {
        "name": "Qatar",
        "aliases": ["QAT", "Qatar", "State of Qatar", "QA"],
    },
    "REU": {
        "name": "Réunion",
        "aliases": ["REU", "Reunion", "Reunion Island", "Réunion"],
    },
    "ROU": {
        "name": "Romania",
        "aliases": ["ROU", "Romania", "ROM", "RUM"],
    },
    "RSA": {
        "name": "South Africa",
        "aliases": ["RSA", "ZAF", "South Africa", "Republic of South Africa"],
    },
    "RUS": {
        "name": "Russia",
        "aliases": ["RUS", "Russia", "Russian Federation", "RU"],
    },
    "RWA": {
        "name": "Rwanda",
        "aliases": ["RWA", "Rwanda", "Republic of Rwanda", "RW"],
    },
    "SAM": {
        "name": "Samoa",
        "aliases": ["SAM", "WSM", "Samoa", "Independent State of Samoa", "Western Samoa"],
    },
    "SCG": {
        "name": "Serbia & Montenegro",
        "aliases": ["SCG", "Serbia & Montenegro", "Serbia and Montenegro"],
    },
    "SCO": {
        "name": "Scotland",
        "aliases": ["SCO", "SCT", "Scotland", "Alba"],
    },
    "SEN": {
        "name": "Senegal",
        "aliases": ["SEN", "Senegal", "Republic of Senegal"],
    },
    "SEY": {
        "name": "Seychelles",
        "aliases": ["SEY", "SYC", "Seychelles", "Republic of Seychelles"],
    },
    "SGP": {
        "name": "Singapore",
        "aliases": ["SGP", "Singapore", "Republic of Singapore"],
    },
    "SKN": {
        "name": "St Kitts & Nevis",
        "aliases": ["SKN", "KNA", "St. Kitts & Nevis", "St. Kitts", "Nevis"],
    },
    "SLE": {
        "name": "Sierra Leone",
        "aliases": ["SLE", "Sierra Leone", "Republic of Sierra Leone", "SL"],
    },
    "SLO": {
        "name": "Slovenia",
        "aliases": ["SLO", "SVN", "Slovenia", "Republic of Slovenia", "Slovenija"],
    },
    "SMR": {
        "name": "San Marino",
        "aliases": ["SMR", "San Marino", "Republic of San Marino"],
    },
    "SOL": {
        "name": "Solomon Islands",
        "aliases": ["SOL", "SLB", "Solomon Islands"],
    },
    "SOM": {
        "name": "Somalia",
        "aliases": ["SOM", "Somalia", "Federal Republic of Somalia"],
    },
    "SRB": {
        "name": "Serbia",
        "aliases": ["SRB", "Serbia", "Republic of Serbia", "Srbija"],
    },
    "SRI": {
        "name": "Sri Lanka",
        "aliases": ["SRI", "LKA", "Ceylon", "Sri Lanka"],
    },
    "SSD": {
        "name": "South Sudan",
        "aliases": ["SSD", "South Sudan", "Republic of South Sudan", "SS"],
    },
    "STP": {
        "name": "Sao Tome & Principe",
        "aliases": ["STP", "Sao Tome & Principe", "Sao Tome", "Principe"],
    },
    "SUD": {
        "name": "Sudan",
        "aliases": ["SUD", "SDN", "Sudan", "Republic of the Sudan"],
    },
    "SUI": {
        "name": "Switzerland",
        "aliases": ["SUI", "CHE", "Switzerland", "Swiss Confederation", "Suisse", "Schweiz"],
    },
    "SUR": {
        "name": "Suriname",
        "aliases": ["SUR", "Suriname", "Republic of Suriname"],
    },
    "SVK": {
        "name": "Slovakia",
        "aliases": ["SVK", "Slovakia", "Slovak Republic", "Slovensko"],
    },
    "SWE": {
        "name": "Sweden",
        "aliases": ["SWE", "Sweden", "Kingdom of Sweden", "Sverige"],
    },
    "SWZ": {
        "name": "Eswatini",
        "aliases": ["SWZ", "Eswatini", "Kingdom of Eswatini", "SZ", "Swaziland", "SWT"],
    },
    "SXM": {
        "name": "Sint Maarten",
        "aliases": ["SXM", "Sint Maarten", "Maarten"],
    },
    "SYR": {
        "name": "Syria",
        "aliases": ["SYR", "Syria", "Syrian Arab Republic"],
    },
    "TAH": {
        "name": "French Polynesia",
        "aliases": ["TAH", "PYF", "French Polynesia", "Tahiti", "Polynesia"],
    },
    "TAN": {
        "name": "Tanzania",
        "aliases": ["TAN", "TZA", "Tanzania", "United Republic of Tanzania", "TZ"],
    },
    "TCH": {
        "name": "Czechoslovakia",
        "aliases": ["TCH", "Czechoslovakia", "Ceskoslovensko"],
    },
    "TCI": {
        "name": "Turks & Caicos Islands",
        "aliases": ["TCI", "TCA", "Turks & Caicos Islands", "Turks & Caicos"],
    },
    "TGA": {
        "name": "Tonga",
        "aliases": ["TGA", "TON", "Tonga", "Kingdom of Tonga"],
    },
    "THA": {
        "name": "Thailand",
        "aliases": ["THA", "Thailand", "Kingdom of Thailand", "TH", "Thai", "Siam"],
    },
    "TJK": {
        "name": "Tajikistan",
        "aliases": ["TJK", "Tajikistan", "Republic of Tajikistan", "TJ"],
    },
    "TKL": {
        "name": "Tokelau",
        "aliases": ["TKL", "Tokelau"],
    },
    "TKM": {
        "name": "Turkmenistan",
        "aliases": ["TKM", "Turkmenistan"],
    },
    "TLS": {
        "name": "Timor-Leste",
        "aliases": ["TLS", "Timor-Leste", "East Timor", "Timor Leste"],
    },
    "TOG": {
        "name": "Togo",
        "aliases": ["TOG", "TGO", "Togo", "Togolese Republic", "TG"],
    },
    "TPE": {
        "name": "Chinese Taipei",
        "aliases": ["TPE", "TWN", "Taiwan", "Chinese Taipei", "Republic of China"],
    },
    "TTO": {
        "name": "Trinidad & Tobago",
        "aliases": ["TTO", "Trinidad & Tobago", "Republic of Trinidad & Tobago", "TT", "Trinidad", "Tobago"],
    },
    "TUN": {
        "name": "Tunisia",
        "aliases": ["TUN", "Tunisia", "Tunisian Republic", "TN"],
    },
    "TUR": {
        "name": "Turkey",
        "aliases": ["TUR", "Turkiye", "Republic of Turkiye", "TR", "Turkey"],
    },
    "TUV": {
        "name": "Tuvalu",
        "aliases": ["TUV", "Tuvalu", "TV"],
    },
    "UAE": {
        "name": "United Arab Emirates",
        "aliases": ["UAE", "ARE", "United Arab Emirates", "AE", "Emirates"],
    },
    "UGA": {
        "name": "Uganda",
        "aliases": ["UGA", "Uganda", "Republic of Uganda", "UG"],
    },
    "UKR": {
        "name": "Ukraine",
        "aliases": ["UKR", "Ukraine", "Ukraina"],
    },
    "URS": {
        "name": "Soviet Union",
        "aliases": ["URS", "SUN", "Soviet Union", "USSR", "CCCP"],
    },
    "URU": {
        "name": "Uruguay",
        "aliases": ["URU", "URY", "Uruguay", "Oriental Republic of Uruguay"],
    },
    "USA": {
        "name": "United States",
        "aliases": ["USA", "United States", "United States of America", "US", "America"],
    },
    "UZB": {
        "name": "Uzbekistan",
        "aliases": ["UZB", "Uzbekistan", "Republic of Uzbekistan", "UZ"],
    },
    "VAN": {
        "name": "Vanuatu",
        "aliases": ["VAN", "VUT", "Vanuatu", "Republic of Vanuatu", "New Hebrides"],
    },
    "VEN": {
        "name": "Venezuela",
        "aliases": ["VEN", "Venezuela", "Bolivarian Republic of Venezuela"],
    },
    "VIE": {
        "name": "Vietnam",
        "aliases": ["VIE", "VNM", "Vietnam", "Socialist Republic of Vietnam", "South Vietnam"],
    },
    "VIN": {
        "name": "St Vincent & the Grenadines",
        "aliases": ["VIN", "VCT", "St. Vincent & the Grenadines", "St. Vincent", "The Grenadines"],
    },
    "WAL": {
        "name": "Wales",
        "aliases": ["WAL", "WLS", "Wales", "Cymru"],
    },
    "WLF": {
        "name": "Wallis & Futuna",
        "aliases": ["WLF", "WF", "Wallis & Futuna"],
    },
    "YEM": {
        "name": "Yemen",
        "aliases": ["YEM", "Yemen", "Republic of Yemen", "YE", "North Yemen", "South Yemen"],
    },
    "YUG": {
        "name": "Yugoslavia",
        "aliases": ["YUG", "Yugoslavia", "SFR Yugoslavia", "FR Yugoslavia"],
    },
    "ZAM": {
        "name": "Zambia",
        "aliases": ["ZAM", "ZMB", "Zambia", "Republic of Zambia"],
    },
    "ZIM": {
        "name": "Zimbabwe",
        "aliases": ["ZIM", "ZWE", "Zimbabwe", "Republic of Zimbabwe", "Rhodesia"],
    },
}


# ============================================================================
# DERIVED VALUE SETS
# ============================================================================

VALID_COUNTRY_CODES = frozenset(COUNTRIES.keys())