"""
The Glass - Country Registry

Canonical country metadata derived from countries.json.
"""

from typing import Dict, List, Optional, TypedDict


class CountryDef(TypedDict):
    name: str
    aliases: List[str]
    sovereign: Optional[str]


COUNTRIES: Dict[str, CountryDef] = {
    'AFG': {
        'name': '',
        'aliases': ['AFG', 'Afghanistan', 'Islamic Republic of Afghanistan', 'Afganistan'],
        'sovereign': None,
    },
    'ALB': {
        'name': '',
        'aliases': ['ALB', 'Albania', 'Republic of Albania'],
        'sovereign': None,
    },
    'ALG': {
        'name': '',
        'aliases': ['ALG', 'DZA', 'Algeria', "People's Democratic Republic of Algeria", 'Democratic Republic of Algeria'],
        'sovereign': None,
    },
    'AND': {
        'name': '',
        'aliases': ['AND', 'Andorra', 'Principality of Andorra'],
        'sovereign': None,
    },
    'ANG': {
        'name': '',
        'aliases': ['ANG', 'AGO', 'Angola', 'Republic of Angola'],
        'sovereign': None,
    },
    'ANT': {
        'name': '',
        'aliases': ['ANT', 'ATG', 'Antigua & Barbuda', 'Antigua', 'Barbuda'],
        'sovereign': None,
    },
    'ARG': {
        'name': '',
        'aliases': ['ARG', 'Argentina', 'Argentine Republic'],
        'sovereign': None,
    },
    'ARM': {
        'name': '',
        'aliases': ['ARM', 'Armenia', 'Republic of Armenia'],
        'sovereign': None,
    },
    'ARU': {
        'name': '',
        'aliases': ['ARU', 'ABW', 'Aruba'],
        'sovereign': 'NED',
    },
    'ASA': {
        'name': '',
        'aliases': ['ASA', 'ASM', 'American Samoa'],
        'sovereign': 'USA',
    },
    'AUS': {
        'name': '',
        'aliases': ['AUS', 'Australia', 'Commonwealth of Australia', 'NIS', 'NFK', 'Norfolk Island', 'Territory of Norfolk Island', 'CXR', 'Christmas Island', 'Territory of Christmas Island', 'CCK', 'Cocos Islands', 'Territory of the Cocos Islands'],
        'sovereign': None,
    },
    'AUT': {
        'name': '',
        'aliases': ['AUT', 'Austria', 'Republic of Austria'],
        'sovereign': None,
    },
    'AZE': {
        'name': '',
        'aliases': ['AZE', 'Azerbaijan', 'Republic of Azerbaijan', 'AZ'],
        'sovereign': None,
    },
    'BAH': {
        'name': '',
        'aliases': ['BAH', 'BHS', 'Bahamas', 'Commonwealth of the Bahamas', 'The Bahamas'],
        'sovereign': None,
    },
    'BAN': {
        'name': '',
        'aliases': ['BAN', 'BGD', 'Bangladesh', "People's Republic of Bangladesh"],
        'sovereign': None,
    },
    'BAR': {
        'name': '',
        'aliases': ['BAR', 'BRB', 'Barbados'],
        'sovereign': None,
    },
    'BDI': {
        'name': '',
        'aliases': ['BDI', 'Burundi', 'Republic of Burundi'],
        'sovereign': None,
    },
    'BEL': {
        'name': '',
        'aliases': ['BEL', 'Belgium', 'Kingdom of Belgium', 'BE'],
        'sovereign': None,
    },
    'BEN': {
        'name': '',
        'aliases': ['BEN', 'Benin', 'Republic of Benin'],
        'sovereign': None,
    },
    'BER': {
        'name': '',
        'aliases': ['BER', 'BMU', 'Bermuda', 'The Islands of Bermuda', 'The Bermudas', 'Bermudas'],
        'sovereign': 'GBR',
    },
    'BHU': {
        'name': '',
        'aliases': ['BHU', 'BTN', 'Bhutan', 'Kingdom of Bhutan'],
        'sovereign': None,
    },
    'BIH': {
        'name': '',
        'aliases': ['BIH', 'Bosnia & Herzegovina', 'Bosnia-Herzegovina', 'Bosnia Herzegovina', 'Bosnia', 'Herzegovina'],
        'sovereign': None,
    },
    'BIZ': {
        'name': '',
        'aliases': ['BIZ', 'BLZ', 'Belize'],
        'sovereign': None,
    },
    'BLR': {
        'name': '',
        'aliases': ['BLR', 'Belarus', 'Republic of Belarus'],
        'sovereign': None,
    },
    'BOL': {
        'name': '',
        'aliases': ['BOL', 'Bolivia', 'Plurinational State of Bolivia'],
        'sovereign': None,
    },
    'BOT': {
        'name': '',
        'aliases': ['BOT', 'BWA', 'Botswana', 'Republic of Botswana'],
        'sovereign': None,
    },
    'BRA': {
        'name': '',
        'aliases': ['BRA', 'Brazil', 'Federative Republic of Brazil', 'BR'],
        'sovereign': None,
    },
    'BRN': {
        'name': '',
        'aliases': ['BRN', 'BHR', 'Bahrain', 'Kingdom of Bahrain'],
        'sovereign': None,
    },
    'BRU': {
        'name': '',
        'aliases': ['BRU', 'Brunei', 'Nation of Brunei Abode of Peace', 'Brunei Darussalam', 'Nation of Brunei'],
        'sovereign': None,
    },
    'BUL': {
        'name': '',
        'aliases': ['BUL', 'BGR', 'Bulgaria', 'Republic of Bulgaria'],
        'sovereign': None,
    },
    'BUR': {
        'name': '',
        'aliases': ['BUR', 'BFA', 'Burkina Faso', 'BF', 'Burkina'],
        'sovereign': None,
    },
    'CAF': {
        'name': '',
        'aliases': ['CAF', 'CAR', 'Central African Republic'],
        'sovereign': None,
    },
    'CAL': {
        'name': '',
        'aliases': ['CAL', 'NCL', 'New Caledonia', 'Caledonia'],
        'sovereign': 'FRA',
    },
    'CAM': {
        'name': '',
        'aliases': ['CAM', 'KHM', 'Cambodia', 'Kingdom of Cambodia'],
        'sovereign': None,
    },
    'CAN': {
        'name': '',
        'aliases': ['CAN', 'Canada', 'CA'],
        'sovereign': None,
    },
    'CAY': {
        'name': '',
        'aliases': ['CAY', 'CYM', 'Cayman Islands', 'Cayman'],
        'sovereign': 'GBR',
    },
    'CGO': {
        'name': '',
        'aliases': ['CGO', 'COG', 'Congo', 'Republic of the Congo'],
        'sovereign': None,
    },
    'CHA': {
        'name': '',
        'aliases': ['CHA', 'TCD', 'Chad', 'Republic of Chad'],
        'sovereign': None,
    },
    'CHI': {
        'name': '',
        'aliases': ['CHI', 'CHL', 'Chile', 'Republic of Chile'],
        'sovereign': None,
    },
    'CHN': {
        'name': '',
        'aliases': ['CHN', 'China', "People's Republic of China"],
        'sovereign': None,
    },
    'CIV': {
        'name': '',
        'aliases': ['CIV', 'Ivory Coast', "Republic of Cote d'Ivoire", "Cote d'Ivoire", 'Republic of Ivory Coast'],
        'sovereign': None,
    },
    'CMR': {
        'name': '',
        'aliases': ['CMR', 'Cameroon', 'Republic of Cameroon'],
        'sovereign': None,
    },
    'COD': {
        'name': '',
        'aliases': ['COD', 'DR Congo', 'Democratic Republic of the Congo', 'Congo the Democratic Republic of the', 'Democratic Republic of Congo', 'DRC'],
        'sovereign': None,
    },
    'COK': {
        'name': '',
        'aliases': ['COK', 'Cook Islands'],
        'sovereign': 'NZL',
    },
    'COL': {
        'name': '',
        'aliases': ['COL', 'Colombia', 'Republic of Colombia'],
        'sovereign': None,
    },
    'COM': {
        'name': '',
        'aliases': ['COM', 'Comoros', 'Union of the Comoros'],
        'sovereign': None,
    },
    'CPV': {
        'name': '',
        'aliases': ['CPV', 'Cape Verde', 'Republic of Cabo Verde', 'CV'],
        'sovereign': None,
    },
    'CRC': {
        'name': '',
        'aliases': ['CRC', 'CRI', 'Costa Rica', 'Republic of Costa Rica', 'CR'],
        'sovereign': None,
    },
    'CRO': {
        'name': '',
        'aliases': ['CRO', 'HRV', 'Croatia', 'Republic of Croatia'],
        'sovereign': None,
    },
    'CUB': {
        'name': '',
        'aliases': ['CUB', 'Cuba', 'Republic of Cuba'],
        'sovereign': None,
    },
    'CYP': {
        'name': '',
        'aliases': ['CYP', 'Cyprus', 'Republic of Cyprus'],
        'sovereign': None,
    },
    'CZE': {
        'name': '',
        'aliases': ['CZE', 'Czechia', 'Czech Republic', 'Czech'],
        'sovereign': None,
    },
    'DEN': {
        'name': '',
        'aliases': ['DEN', 'DNK', 'Denmark', 'Kingdom of Denmark', 'GRL', 'Greenland', 'FRO', 'Faroe Islands'],
        'sovereign': None,
    },
    'DJI': {
        'name': '',
        'aliases': ['DJI', 'Djibouti', 'Republic of Djibouti'],
        'sovereign': None,
    },
    'DMA': {
        'name': '',
        'aliases': ['DMA', 'Dominica', 'Commonwealth of Dominica'],
        'sovereign': None,
    },
    'DOM': {
        'name': '',
        'aliases': ['DOM', 'Dominican Republic'],
        'sovereign': None,
    },
    'ECU': {
        'name': '',
        'aliases': ['ECU', 'Ecuador', 'Republic of Ecuador'],
        'sovereign': None,
    },
    'EGY': {
        'name': '',
        'aliases': ['EGY', 'Egypt', 'Arab Republic of Egypt', 'Republic of Egypt'],
        'sovereign': None,
    },
    'ERI': {
        'name': '',
        'aliases': ['ERI', 'Eritrea', 'State of Eritrea'],
        'sovereign': None,
    },
    'ESA': {
        'name': '',
        'aliases': ['ESA', 'SLV', 'El Salvador', 'Republic of El Salvador'],
        'sovereign': None,
    },
    'ESP': {
        'name': '',
        'aliases': ['ESP', 'Spain', 'Kingdom of Spain'],
        'sovereign': None,
    },
    'EST': {
        'name': '',
        'aliases': ['EST', 'Estonia', 'Republic of Estonia'],
        'sovereign': None,
    },
    'ETH': {
        'name': '',
        'aliases': ['ETH', 'Ethiopia', 'Federal Democratic Republic of Ethiopia'],
        'sovereign': None,
    },
    'FIJ': {
        'name': '',
        'aliases': ['FIJ', 'FJI', 'Fiji', 'Republic of Fiji'],
        'sovereign': None,
    },
    'FIN': {
        'name': '',
        'aliases': ['FIN', 'Finland', 'Republic of Finland', 'ALA', 'Aland Islands', 'Aaland', 'Aland'],
        'sovereign': None,
    },
    'FRA': {
        'name': '',
        'aliases': ['FRA', 'France', 'French Republic', 'FR', 'GUF', 'French Guiana', 'Guiana', 'GLP', 'Guadeloupe', 'MTQ', 'Martinique', 'MYT', 'Mayotte', 'Department of Mayotte', 'REU', 'Reunion', 'Reunion Island', 'BLM', 'St. Barthelemy', 'Collectivity of St. Barthelemy', 'MAF', 'St. Martin', 'Collectivity of St. Martin', 'SPM', 'St. Pierre & Miquelon', 'Collectivite territoriale de St.-Pierre-et-Miquelon', 'WLF', 'Wallis & Futuna', 'Territory of the Wallis & Futuna Islands', 'WF'],
        'sovereign': None,
    },
    'FSM': {
        'name': '',
        'aliases': ['FSM', 'Micronesia', 'Federated States of Micronesia', 'Micronesia Federated States of'],
        'sovereign': None,
    },
    'GAB': {
        'name': '',
        'aliases': ['GAB', 'Gabon', 'Gabonese Republic'],
        'sovereign': None,
    },
    'GAM': {
        'name': '',
        'aliases': ['GAM', 'GMB', 'Gambia', 'Republic of the Gambia', 'The Gambia'],
        'sovereign': None,
    },
    'GBR': {
        'name': '',
        'aliases': ['GBR', 'United Kingdom', 'United Kingdom of Great Britain & Northern Ireland', 'GB', 'UK', 'Great Britain', 'JEY', 'Jersey', 'Bailiwick of Jersey', 'GGY', 'Guernsey', 'Bailiwick of Guernsey', 'IMN', 'Isle of Man', 'ENG', 'England', 'SCO', 'SCT', 'Scotland', 'WLS', 'Wales', 'PCN', 'Pitcairn Islands', 'Pitcairn Group of Islands', 'SHN', 'St. Helena', 'FLK', 'Falkland Islands', 'FK', 'AIA', 'Anguilla', 'Britain'],
        'sovereign': None,
    },
    'GBS': {
        'name': '',
        'aliases': ['GBS', 'GNB', 'Guinea-Bissau', 'Republic of Guinea-Bissau', 'Guinea Bissau'],
        'sovereign': None,
    },
    'GEO': {
        'name': '',
        'aliases': ['GEO', 'Georgia'],
        'sovereign': None,
    },
    'GEQ': {
        'name': '',
        'aliases': ['GEQ', 'GNQ', 'Equatorial Guinea', 'Republic of Equatorial Guinea'],
        'sovereign': None,
    },
    'GER': {
        'name': '',
        'aliases': ['GER', 'DEU', 'Germany', 'Federal Republic of Germany'],
        'sovereign': None,
    },
    'GHA': {
        'name': '',
        'aliases': ['GHA', 'Ghana', 'Republic of Ghana'],
        'sovereign': None,
    },
    'GIB': {
        'name': '',
        'aliases': ['GIB', 'Gibraltar'],
        'sovereign': 'GBR',
    },
    'GRE': {
        'name': '',
        'aliases': ['GRE', 'GRC', 'Greece', 'Hellenic Republic'],
        'sovereign': None,
    },
    'GRN': {
        'name': '',
        'aliases': ['GRN', 'GRD', 'Grenada'],
        'sovereign': None,
    },
    'GUA': {
        'name': '',
        'aliases': ['GUA', 'GTM', 'Guatemala', 'Republic of Guatemala'],
        'sovereign': None,
    },
    'GUI': {
        'name': '',
        'aliases': ['GUI', 'GIN', 'Guinea', 'Republic of Guinea'],
        'sovereign': None,
    },
    'GUM': {
        'name': '',
        'aliases': ['GUM', 'Guam'],
        'sovereign': 'USA',
    },
    'GUY': {
        'name': '',
        'aliases': ['GUY', 'Guyana', 'Co-operative Republic of Guyana', 'Republic of Guyana'],
        'sovereign': None,
    },
    'HAI': {
        'name': '',
        'aliases': ['HAI', 'HTI', 'Haiti', 'Republic of Haiti'],
        'sovereign': None,
    },
    'HKG': {
        'name': '',
        'aliases': ['HKG', 'Hong Kong', "Hong Kong Special Administrative Region of the People's Republic of China", 'HK', 'Hong Kong China'],
        'sovereign': 'CHN',
    },
    'HON': {
        'name': '',
        'aliases': ['HON', 'HND', 'Honduras', 'Republic of Honduras'],
        'sovereign': None,
    },
    'HUN': {
        'name': '',
        'aliases': ['HUN', 'Hungary'],
        'sovereign': None,
    },
    'INA': {
        'name': '',
        'aliases': ['INA', 'IDN', 'Indonesia', 'Republic of Indonesia'],
        'sovereign': None,
    },
    'IND': {
        'name': '',
        'aliases': ['IND', 'India', 'Republic of India'],
        'sovereign': None,
    },
    'IRI': {
        'name': '',
        'aliases': ['IRI', 'IRN', 'Iran', 'Islamic Republic of Iran', 'Republic of Iran'],
        'sovereign': None,
    },
    'IRL': {
        'name': '',
        'aliases': ['IRL', 'Ireland', 'Republic of Ireland', 'NIR', 'Northern Ireland'],
        'sovereign': None,
    },
    'IRQ': {
        'name': '',
        'aliases': ['IRQ', 'Iraq', 'Republic of Iraq', 'IQ'],
        'sovereign': None,
    },
    'ISL': {
        'name': '',
        'aliases': ['ISL', 'Iceland', 'Republic of Iceland'],
        'sovereign': None,
    },
    'ISR': {
        'name': '',
        'aliases': ['ISR', 'Israel', 'State of Israel'],
        'sovereign': None,
    },
    'ISV': {
        'name': '',
        'aliases': ['ISV', 'VIR', 'United States Virgin Islands', 'Virgin Islands of the United States', 'Virgin Islands US', 'US Virgin Islands', 'Virgin Islands'],
        'sovereign': 'USA',
    },
    'ITA': {
        'name': '',
        'aliases': ['ITA', 'Italy', 'Italian Republic'],
        'sovereign': None,
    },
    'IVB': {
        'name': '',
        'aliases': ['IVB', 'VGB', 'British Virgin Islands', 'Virgin Islands British'],
        'sovereign': 'GBR',
    },
    'JAM': {
        'name': '',
        'aliases': ['JAM', 'Jamaica', 'JM'],
        'sovereign': None,
    },
    'JOR': {
        'name': '',
        'aliases': ['JOR', 'Jordan', 'Hashemite Kingdom of Jordan', 'Kingdom of Jordan'],
        'sovereign': None,
    },
    'JPN': {
        'name': '',
        'aliases': ['JPN', 'Japan'],
        'sovereign': None,
    },
    'KAZ': {
        'name': '',
        'aliases': ['KAZ', 'Kazakhstan', 'Republic of Kazakhstan'],
        'sovereign': None,
    },
    'KEN': {
        'name': '',
        'aliases': ['KEN', 'Kenya', 'Republic of Kenya', 'KE'],
        'sovereign': None,
    },
    'KGZ': {
        'name': '',
        'aliases': ['KGZ', 'Kyrgyzstan', 'Kyrgyz Republic', 'KG'],
        'sovereign': None,
    },
    'KIR': {
        'name': '',
        'aliases': ['KIR', 'Kiribati', 'Independent & Sovereign Republic of Kiribati', 'KI', 'Republic of Kiribati'],
        'sovereign': None,
    },
    'KOR': {
        'name': '',
        'aliases': ['KOR', 'South Korea', 'Republic of Korea', 'Korea Republic of', 'Korea'],
        'sovereign': None,
    },
    'KOS': {
        'name': '',
        'aliases': ['KOS', 'UNK', 'Kosovo', 'Republic of Kosovo'],
        'sovereign': None,
    },
    'KSA': {
        'name': '',
        'aliases': ['KSA', 'SAU', 'Saudi Arabia', 'Kingdom of Saudi Arabia', 'Saudi', 'Arabia', 'SA'],
        'sovereign': None,
    },
    'KUW': {
        'name': '',
        'aliases': ['KUW', 'KWT', 'Kuwait', 'State of Kuwait', 'KW'],
        'sovereign': None,
    },
    'LAO': {
        'name': '',
        'aliases': ['LAO', 'Laos', "Lao People's Democratic Republic"],
        'sovereign': None,
    },
    'LAT': {
        'name': '',
        'aliases': ['LAT', 'LVA', 'Latvia', 'Republic of Latvia'],
        'sovereign': None,
    },
    'LBA': {
        'name': '',
        'aliases': ['LBA', 'LBY', 'Libya', 'State of Libya'],
        'sovereign': None,
    },
    'LBN': {
        'name': '',
        'aliases': ['LBN', 'Lebanon', 'Lebanese Republic'],
        'sovereign': None,
    },
    'LBR': {
        'name': '',
        'aliases': ['LBR', 'Liberia', 'Republic of Liberia'],
        'sovereign': None,
    },
    'LCA': {
        'name': '',
        'aliases': ['LCA', 'St. Lucia', 'Lucia'],
        'sovereign': None,
    },
    'LES': {
        'name': '',
        'aliases': ['LES', 'LSO', 'Lesotho', 'Kingdom of Lesotho'],
        'sovereign': None,
    },
    'LIE': {
        'name': '',
        'aliases': ['LIE', 'Liechtenstein', 'Principality of Liechtenstein'],
        'sovereign': None,
    },
    'LTU': {
        'name': '',
        'aliases': ['LTU', 'Lithuania', 'Republic of Lithuania'],
        'sovereign': None,
    },
    'LUX': {
        'name': '',
        'aliases': ['LUX', 'Luxembourg', 'Grand Duchy of Luxembourg'],
        'sovereign': None,
    },
    'MAC': {
        'name': '',
        'aliases': ['MAC', 'Macau', 'Macao', 'Macao China', 'Macau China', "Macao Special Administrative Region of the People's Republic of China"],
        'sovereign': 'CHN',
    },
    'MAD': {
        'name': '',
        'aliases': ['MAD', 'MDG', 'Madagascar', 'Republic of Madagascar'],
        'sovereign': None,
    },
    'MAR': {
        'name': '',
        'aliases': ['MAR', 'Morocco', 'Kingdom of Morocco', 'ESH', 'Western Sahara', 'Sahrawi Arab Democratic Republic'],
        'sovereign': None,
    },
    'MAS': {
        'name': '',
        'aliases': ['MAS', 'MYS', 'Malaysia'],
        'sovereign': None,
    },
    'MAT': {
        'name': '',
        'aliases': ['MAT', 'MSR', 'Montserrat'],
        'sovereign': 'GBR',
    },
    'MAW': {
        'name': '',
        'aliases': ['MAW', 'MWI', 'Malawi', 'Republic of Malawi'],
        'sovereign': None,
    },
    'MDA': {
        'name': '',
        'aliases': ['MDA', 'Moldova', 'Republic of Moldova', 'Moldova Republic of'],
        'sovereign': None,
    },
    'MDV': {
        'name': '',
        'aliases': ['MDV', 'Maldives', 'Republic of the Maldives'],
        'sovereign': None,
    },
    'MEX': {
        'name': '',
        'aliases': ['MEX', 'Mexico', 'United Mexican States', 'MX'],
        'sovereign': None,
    },
    'MGL': {
        'name': '',
        'aliases': ['MGL', 'MNG', 'Mongolia'],
        'sovereign': None,
    },
    'MHL': {
        'name': '',
        'aliases': ['MHL', 'Marshall Islands', 'Republic of the Marshall Islands'],
        'sovereign': None,
    },
    'MKD': {
        'name': '',
        'aliases': ['MKD', 'North Macedonia', 'Republic of North Macedonia', 'The former Yugoslav Republic of Macedonia', 'Macedonia', 'Republic of Macedonia'],
        'sovereign': None,
    },
    'MLI': {
        'name': '',
        'aliases': ['MLI', 'Mali', 'Republic of Mali'],
        'sovereign': None,
    },
    'MLT': {
        'name': '',
        'aliases': ['MLT', 'Malta', 'Republic of Malta'],
        'sovereign': None,
    },
    'MNE': {
        'name': '',
        'aliases': ['MNE', 'Montenegro'],
        'sovereign': None,
    },
    'MON': {
        'name': '',
        'aliases': ['MON', 'MCO', 'Monaco', 'Principality of Monaco'],
        'sovereign': None,
    },
    'MOZ': {
        'name': '',
        'aliases': ['MOZ', 'Mozambique', 'Republic of Mozambique'],
        'sovereign': None,
    },
    'MRI': {
        'name': '',
        'aliases': ['MRI', 'MUS', 'Mauritius', 'Republic of Mauritius'],
        'sovereign': None,
    },
    'MTN': {
        'name': '',
        'aliases': ['MTN', 'MRT', 'Mauritania', 'Islamic Republic of Mauritania'],
        'sovereign': None,
    },
    'MYA': {
        'name': '',
        'aliases': ['MYA', 'MMR', 'Myanmar', 'Republic of the Union of Myanmar', 'Burma'],
        'sovereign': None,
    },
    'NAM': {
        'name': '',
        'aliases': ['NAM', 'Namibia', 'Republic of Namibia'],
        'sovereign': None,
    },
    'NCA': {
        'name': '',
        'aliases': ['NCA', 'NIC', 'Nicaragua', 'Republic of Nicaragua'],
        'sovereign': None,
    },
    'NED': {
        'name': '',
        'aliases': ['NED', 'NLD', 'Netherlands', 'Kingdom of the Netherlands', 'Holland', 'The Netherlands', 'Caribbean Netherlands', 'BES', 'BES islands', 'Bonaire', 'Sint Eustatius', 'Saba', 'Bonaire Sint Eustatius and Saba', 'Eustatius', 'CUW', 'Curacao', 'Country of Curacao', 'SXM', 'Sint Maarten', 'Maarten'],
        'sovereign': None,
    },
    'NEP': {
        'name': '',
        'aliases': ['NEP', 'NPL', 'Nepal', 'Federal Democratic Republic of Nepal'],
        'sovereign': None,
    },
    'NGR': {
        'name': '',
        'aliases': ['NGR', 'NGA', 'Nigeria', 'Federal Republic of Nigeria'],
        'sovereign': None,
    },
    'NIG': {
        'name': '',
        'aliases': ['NIG', 'NER', 'Niger', 'Republic of Niger'],
        'sovereign': None,
    },
    'NMI': {
        'name': '',
        'aliases': ['NMI', 'MNP', 'Northern Mariana Islands', 'Commonwealth of the Northern Mariana Islands'],
        'sovereign': 'USA',
    },
    'NOR': {
        'name': '',
        'aliases': ['NOR', 'Norway', 'Kingdom of Norway', 'NO'],
        'sovereign': None,
    },
    'NRU': {
        'name': '',
        'aliases': ['NRU', 'Nauru', 'Republic of Nauru'],
        'sovereign': None,
    },
    'NZL': {
        'name': '',
        'aliases': ['NZL', 'New Zealand', 'NZ', 'TKL', 'Tokelau', 'NIU', 'Niue'],
        'sovereign': None,
    },
    'OMA': {
        'name': '',
        'aliases': ['OMA', 'OMN', 'Oman', 'Sultanate of Oman'],
        'sovereign': None,
    },
    'PAK': {
        'name': '',
        'aliases': ['PAK', 'Pakistan', 'Islamic Republic of Pakistan', 'Republic of Pakistan'],
        'sovereign': None,
    },
    'PAN': {
        'name': '',
        'aliases': ['PAN', 'Panama', 'Republic of Panama'],
        'sovereign': None,
    },
    'PAR': {
        'name': '',
        'aliases': ['PAR', 'PRY', 'Paraguay', 'Republic of Paraguay'],
        'sovereign': None,
    },
    'PER': {
        'name': '',
        'aliases': ['PER', 'Peru', 'Republic of Peru'],
        'sovereign': None,
    },
    'PHI': {
        'name': '',
        'aliases': ['PHI', 'PHL', 'Philippines', 'Republic of the Philippines'],
        'sovereign': None,
    },
    'PLE': {
        'name': '',
        'aliases': ['PLE', 'PSE', 'Palestine', 'State of Palestine', 'Palestine State of'],
        'sovereign': None,
    },
    'PLW': {
        'name': '',
        'aliases': ['PLW', 'Palau', 'Republic of Palau'],
        'sovereign': None,
    },
    'PNG': {
        'name': '',
        'aliases': ['PNG', 'Papua New Guinea', 'Independent State of Papua New Guinea'],
        'sovereign': None,
    },
    'POL': {
        'name': '',
        'aliases': ['POL', 'Poland', 'Republic of Poland'],
        'sovereign': None,
    },
    'POR': {
        'name': '',
        'aliases': ['POR', 'PRT', 'Portugal', 'Portuguese Republic'],
        'sovereign': None,
    },
    'PRK': {
        'name': '',
        'aliases': ['PRK', 'North Korea', "Democratic People's Republic of Korea", 'DPRK', 'Korea DPR'],
        'sovereign': None,
    },
    'PUR': {
        'name': '',
        'aliases': ['PUR', 'PRI', 'Puerto Rico', 'Commonwealth of Puerto Rico', 'PR'],
        'sovereign': 'USA',
    },
    'QAT': {
        'name': '',
        'aliases': ['QAT', 'Qatar', 'State of Qatar', 'QA'],
        'sovereign': None,
    },
    'ROU': {
        'name': '',
        'aliases': ['ROU', 'Romania'],
        'sovereign': None,
    },
    'RSA': {
        'name': '',
        'aliases': ['RSA', 'ZAF', 'South Africa', 'Republic of South Africa'],
        'sovereign': None,
    },
    'RUS': {
        'name': '',
        'aliases': ['RUS', 'Russia', 'Russian Federation', 'RU'],
        'sovereign': None,
    },
    'RWA': {
        'name': '',
        'aliases': ['RWA', 'Rwanda', 'Republic of Rwanda', 'RW'],
        'sovereign': None,
    },
    'SAM': {
        'name': '',
        'aliases': ['SAM', 'WSM', 'Samoa', 'Independent State of Samoa', 'State of Samoa'],
        'sovereign': None,
    },
    'SEN': {
        'name': '',
        'aliases': ['SEN', 'Senegal', 'Republic of Senegal'],
        'sovereign': None,
    },
    'SEY': {
        'name': '',
        'aliases': ['SEY', 'SYC', 'Seychelles', 'Republic of Seychelles'],
        'sovereign': None,
    },
    'SGP': {
        'name': '',
        'aliases': ['SGP', 'Singapore', 'Republic of Singapore'],
        'sovereign': None,
    },
    'SKN': {
        'name': '',
        'aliases': ['SKN', 'KNA', 'St. Kitts & Nevis', 'St. Kitts', 'Federation of St. Christopher & Nevis', 'KN', 'Kitts & Nevis', 'Kitts', 'St. Nevis', 'Nevis'],
        'sovereign': None,
    },
    'SLE': {
        'name': '',
        'aliases': ['SLE', 'Sierra Leone', 'Republic of Sierra Leone', 'SL'],
        'sovereign': None,
    },
    'SLO': {
        'name': '',
        'aliases': ['SLO', 'SVN', 'Slovenia', 'Republic of Slovenia'],
        'sovereign': None,
    },
    'SMR': {
        'name': '',
        'aliases': ['SMR', 'San Marino', 'Most Serene Republic of San Marino', 'SM', 'Republic of San Marino'],
        'sovereign': None,
    },
    'SOL': {
        'name': '',
        'aliases': ['SOL', 'SLB', 'Solomon Islands'],
        'sovereign': None,
    },
    'SOM': {
        'name': '',
        'aliases': ['SOM', 'Somalia', 'Federal Republic of Somalia'],
        'sovereign': None,
    },
    'SRB': {
        'name': '',
        'aliases': ['SRB', 'Serbia', 'Republic of Serbia'],
        'sovereign': None,
    },
    'SRI': {
        'name': '',
        'aliases': ['SRI', 'LKA', 'Sri Lanka', 'Democratic Socialist Republic of Sri Lanka'],
        'sovereign': None,
    },
    'SSD': {
        'name': '',
        'aliases': ['SSD', 'South Sudan', 'Republic of South Sudan', 'SS'],
        'sovereign': None,
    },
    'STP': {
        'name': '',
        'aliases': ['STP', 'Sao Tome & Principe', 'Democratic Republic of Sao Tome & Principe'],
        'sovereign': None,
    },
    'SUD': {
        'name': '',
        'aliases': ['SUD', 'SDN', 'Sudan', 'Republic of the Sudan', 'Republic of Sudan'],
        'sovereign': None,
    },
    'SUI': {
        'name': '',
        'aliases': ['SUI', 'CHE', 'Switzerland', 'Swiss Confederation'],
        'sovereign': None,
    },
    'SUR': {
        'name': '',
        'aliases': ['SUR', 'Suriname', 'Republic of Suriname'],
        'sovereign': None,
    },
    'SVK': {
        'name': '',
        'aliases': ['SVK', 'Slovakia', 'Slovak Republic'],
        'sovereign': None,
    },
    'SWE': {
        'name': '',
        'aliases': ['SWE', 'Sweden', 'Kingdom of Sweden'],
        'sovereign': None,
    },
    'SWZ': {
        'name': '',
        'aliases': ['SWZ', 'Eswatini', 'Kingdom of Eswatini', 'SZ', 'Swaziland'],
        'sovereign': None,
    },
    'SYR': {
        'name': '',
        'aliases': ['SYR', 'Syria', 'Syrian Arab Republic'],
        'sovereign': None,
    },
    'TAH': {
        'name': '',
        'aliases': ['TAH', 'PYF', 'French Polynesia', 'Tahiti', 'Polynesia'],
        'sovereign': 'FRA',
    },
    'TAN': {
        'name': '',
        'aliases': ['TAN', 'TZA', 'Tanzania', 'United Republic of Tanzania', 'TZ', 'Tanzania United Republic of'],
        'sovereign': None,
    },
    'TCI': {
        'name': '',
        'aliases': ['TCI', 'TCA', 'Turks & Caicos Islands', 'Turks', 'Caicos', 'Turks & Caicos', 'Caicos Islands', 'Turks Islands'],
        'sovereign': 'GBR',
    },
    'TGA': {
        'name': '',
        'aliases': ['TGA', 'TON', 'Tonga', 'Kingdom of Tonga'],
        'sovereign': None,
    },
    'THA': {
        'name': '',
        'aliases': ['THA', 'Thailand', 'Kingdom of Thailand', 'TH', 'Thai'],
        'sovereign': None,
    },
    'TJK': {
        'name': '',
        'aliases': ['TJK', 'Tajikistan', 'Republic of Tajikistan', 'TJ'],
        'sovereign': None,
    },
    'TKM': {
        'name': '',
        'aliases': ['TKM', 'Turkmenistan'],
        'sovereign': None,
    },
    'TLS': {
        'name': '',
        'aliases': ['TLS', 'Timor-Leste', 'Democratic Republic of Timor-Leste', 'East Timor', 'Timor', 'Timor Leste'],
        'sovereign': None,
    },
    'TOG': {
        'name': '',
        'aliases': ['TOG', 'TGO', 'Togo', 'Togolese Republic', 'TG', 'Togolese'],
        'sovereign': None,
    },
    'TPE': {
        'name': '',
        'aliases': ['TPE', 'TWN', 'Taiwan', 'Republic of China Taiwan', 'TW', 'Republic of China', 'Chinese Taipei', 'Taiwan China'],
        'sovereign': None,
    },
    'TTO': {
        'name': '',
        'aliases': ['TTO', 'Trinidad & Tobago', 'Republic of Trinidad & Tobago', 'TT', 'Trinidad', 'Tobago', 'Trinidad Tobago'],
        'sovereign': None,
    },
    'TUN': {
        'name': '',
        'aliases': ['TUN', 'Tunisia', 'Tunisian Republic', 'TN', 'Republic of Tunisia'],
        'sovereign': None,
    },
    'TUR': {
        'name': '',
        'aliases': ['TUR', 'Turkiye', 'Republic of Turkiye', 'TR', 'Republic of Turkey', 'Turkey'],
        'sovereign': None,
    },
    'TUV': {
        'name': '',
        'aliases': ['TUV', 'Tuvalu', 'TV'],
        'sovereign': None,
    },
    'UAE': {
        'name': '',
        'aliases': ['UAE', 'ARE', 'United Arab Emirates', 'AE', 'Arab Emirates', 'Emirates'],
        'sovereign': None,
    },
    'UGA': {
        'name': '',
        'aliases': ['UGA', 'Uganda', 'Republic of Uganda', 'UG'],
        'sovereign': None,
    },
    'UKR': {
        'name': '',
        'aliases': ['UKR', 'Ukraine'],
        'sovereign': None,
    },
    'URU': {
        'name': '',
        'aliases': ['URU', 'URY', 'Uruguay', 'Oriental Republic of Uruguay', 'Republic of Uruguay'],
        'sovereign': None,
    },
    'USA': {
        'name': '',
        'aliases': ['USA', 'United States', 'United States of America', 'US', 'America'],
        'sovereign': None,
    },
    'UZB': {
        'name': '',
        'aliases': ['UZB', 'Uzbekistan', 'Republic of Uzbekistan', 'UZ'],
        'sovereign': None,
    },
    'VAN': {
        'name': '',
        'aliases': ['VAN', 'VUT', 'Vanuatu', 'Republic of Vanuatu'],
        'sovereign': None,
    },
    'VEN': {
        'name': '',
        'aliases': ['VEN', 'Venezuela', 'Bolivarian Republic of Venezuela', 'Venezuela Bolivarian Republic of'],
        'sovereign': None,
    },
    'VIE': {
        'name': '',
        'aliases': ['VIE', 'VNM', 'Vietnam', 'Socialist Republic of Vietnam', 'Republic of Vietnam'],
        'sovereign': None,
    },
    'VIN': {
        'name': '',
        'aliases': ['VIN', 'VCT', 'St. Vincent & the Grenadines', 'St. Vincent', 'The Grenadines'],
        'sovereign': None,
    },
    'YEM': {
        'name': '',
        'aliases': ['YEM', 'Yemen', 'Republic of Yemen', 'YE', 'Yemeni Republic'],
        'sovereign': None,
    },
    'ZAM': {
        'name': '',
        'aliases': ['ZAM', 'ZMB', 'Zambia', 'Republic of Zambia'],
        'sovereign': None,
    },
    'ZIM': {
        'name': '',
        'aliases': ['ZIM', 'ZWE', 'Zimbabwe', 'Republic of Zimbabwe'],
        'sovereign': None,
    },
}
