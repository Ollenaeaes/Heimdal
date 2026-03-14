"""Platform-wide constants: MID-to-flag lookup, scoring rules, severity levels.

All values are module-level and should be treated as immutable.
"""

# ---------------------------------------------------------------------------
# Severity point values
# ---------------------------------------------------------------------------
SEVERITY_POINTS: dict[str, int] = {
    "critical": 25,
    "high": 15,
    "moderate": 8,
    "low": 3,
}

# ---------------------------------------------------------------------------
# Maximum points per rule (caps prevent a single rule from dominating)
# 5 GFW-sourced + 13 real-time = 18+ rules
# ---------------------------------------------------------------------------
MAX_PER_RULE: dict[str, int] = {
    # GFW-sourced rules — cap at max single firing
    "gfw_ais_disabling": 100,
    "gfw_encounter": 100,
    "gfw_loitering": 40,
    "gfw_port_visit": 40,
    "gfw_dark_sar": 40,
    # Real-time rules — cap at max single firing
    "ais_gap": 40,
    "sts_proximity": 40,
    "destination_spoof": 40,
    "draft_change": 40,
    "flag_hopping": 40,
    "sanctions_match": 100,
    "vessel_age": 40,
    "speed_anomaly": 10,
    "identity_mismatch": 100,
    "flag_of_convenience": 40,
    "ais_spoofing": 100,
    "ownership_risk": 60,
    "insurance_class_risk": 60,
    # GFW-sourced enrichment rule
    "voyage_pattern": 80,
}

# All rule IDs as a frozenset for validation
ALL_RULE_IDS: frozenset[str] = frozenset(MAX_PER_RULE.keys())

# ---------------------------------------------------------------------------
# MID (Maritime Identification Digits) to ISO 3166-1 alpha-2 country code
# Source: ITU Maritime Identification Digits assignments
# https://www.itu.int/en/ITU-R/terrestrial/fmd/Pages/mid.aspx
# ---------------------------------------------------------------------------
MID_TO_FLAG: dict[int, str] = {
    # Europe
    201: "AL",  # Albania
    202: "AD",  # Andorra
    203: "AT",  # Austria
    204: "PT",  # Azores (Portugal)
    205: "BE",  # Belgium
    206: "BY",  # Belarus
    207: "BG",  # Bulgaria
    208: "VA",  # Vatican
    209: "CY",  # Cyprus
    210: "CY",  # Cyprus
    211: "DE",  # Germany
    212: "CY",  # Cyprus
    213: "GE",  # Georgia
    214: "MD",  # Moldova
    215: "MT",  # Malta
    216: "AM",  # Armenia
    218: "DE",  # Germany
    219: "DK",  # Denmark
    220: "DK",  # Denmark
    224: "ES",  # Spain
    225: "ES",  # Spain
    226: "FR",  # France
    227: "FR",  # France
    228: "FR",  # France
    229: "MT",  # Malta
    230: "FI",  # Finland
    231: "FO",  # Faroe Islands
    232: "GB",  # United Kingdom
    233: "GB",  # United Kingdom
    234: "GB",  # United Kingdom
    235: "GB",  # United Kingdom
    236: "GI",  # Gibraltar
    237: "GR",  # Greece
    238: "HR",  # Croatia
    239: "GR",  # Greece
    240: "GR",  # Greece
    241: "GR",  # Greece
    242: "MA",  # Morocco
    243: "HU",  # Hungary
    244: "NL",  # Netherlands
    245: "NL",  # Netherlands
    246: "NL",  # Netherlands
    247: "IT",  # Italy
    248: "MT",  # Malta
    249: "MT",  # Malta
    250: "IE",  # Ireland
    251: "IS",  # Iceland
    252: "LI",  # Liechtenstein
    253: "LU",  # Luxembourg
    254: "LU",  # Luxembourg
    255: "PT",  # Portugal
    256: "MT",  # Malta
    257: "NO",  # Norway
    258: "NO",  # Norway
    259: "NO",  # Norway
    261: "PL",  # Poland
    263: "PT",  # Portugal
    264: "RO",  # Romania
    265: "SE",  # Sweden
    266: "SE",  # Sweden
    267: "CZ",  # Czech Republic
    268: "UA",  # Ukraine
    269: "UA",  # Ukraine
    270: "CZ",  # Czech Republic
    271: "TR",  # Turkey
    272: "UA",  # Ukraine
    273: "RU",  # Russia
    274: "MK",  # North Macedonia
    275: "LV",  # Latvia
    276: "EE",  # Estonia
    277: "LT",  # Lithuania
    278: "SI",  # Slovenia
    279: "ME",  # Montenegro
    # North America & Caribbean
    301: "AI",  # Anguilla
    303: "US",  # United States (Alaska)
    304: "AG",  # Antigua and Barbuda
    305: "AG",  # Antigua and Barbuda
    306: "CW",  # Curacao
    307: "AW",  # Aruba
    308: "BS",  # Bahamas
    309: "BS",  # Bahamas
    310: "BM",  # Bermuda
    311: "BS",  # Bahamas
    312: "BZ",  # Belize
    314: "BB",  # Barbados
    316: "CA",  # Canada
    319: "KY",  # Cayman Islands
    321: "CR",  # Costa Rica
    323: "CU",  # Cuba
    325: "DM",  # Dominica
    327: "DO",  # Dominican Republic
    329: "GP",  # Guadeloupe
    330: "GD",  # Grenada
    332: "GT",  # Guatemala
    334: "HN",  # Honduras
    336: "HT",  # Haiti
    338: "US",  # United States
    339: "JM",  # Jamaica
    341: "KN",  # Saint Kitts and Nevis
    343: "LC",  # Saint Lucia
    345: "MX",  # Mexico
    347: "MQ",  # Martinique
    348: "MS",  # Montserrat
    350: "NI",  # Nicaragua
    351: "PA",  # Panama
    352: "PA",  # Panama
    353: "PA",  # Panama
    354: "PA",  # Panama
    355: "PA",  # Panama (additional)
    356: "PA",  # Panama (additional)
    357: "PA",  # Panama (additional)
    358: "PR",  # Puerto Rico
    359: "SV",  # El Salvador
    361: "PM",  # Saint Pierre and Miquelon
    362: "TT",  # Trinidad and Tobago
    364: "TC",  # Turks and Caicos
    366: "US",  # United States
    367: "US",  # United States
    368: "US",  # United States
    369: "US",  # United States
    370: "PA",  # Panama
    371: "PA",  # Panama
    372: "PA",  # Panama
    373: "PA",  # Panama
    374: "PA",  # Panama
    375: "VC",  # Saint Vincent and the Grenadines
    376: "VC",  # Saint Vincent and the Grenadines
    377: "VC",  # Saint Vincent and the Grenadines
    378: "VG",  # British Virgin Islands
    379: "VI",  # US Virgin Islands
    # South America
    401: "AF",  # Afghanistan
    403: "SA",  # Saudi Arabia
    405: "BD",  # Bangladesh
    408: "BH",  # Bahrain
    410: "BT",  # Bhutan
    412: "CN",  # China
    413: "CN",  # China
    414: "CN",  # China
    416: "TW",  # Taiwan
    417: "LK",  # Sri Lanka
    419: "IN",  # India
    422: "IR",  # Iran
    423: "AZ",  # Azerbaijan
    425: "IQ",  # Iraq
    428: "IL",  # Israel
    431: "JP",  # Japan
    432: "JP",  # Japan
    434: "TM",  # Turkmenistan
    436: "KZ",  # Kazakhstan
    437: "UZ",  # Uzbekistan
    438: "JO",  # Jordan
    440: "KR",  # South Korea
    441: "KR",  # South Korea
    443: "PS",  # Palestine
    445: "KP",  # North Korea
    447: "KW",  # Kuwait
    450: "LB",  # Lebanon
    451: "KG",  # Kyrgyzstan
    453: "MO",  # Macau
    455: "MV",  # Maldives
    457: "MN",  # Mongolia
    459: "NP",  # Nepal
    461: "OM",  # Oman
    463: "PK",  # Pakistan
    466: "QA",  # Qatar
    468: "SY",  # Syria
    470: "AE",  # United Arab Emirates
    471: "AE",  # United Arab Emirates
    472: "TJ",  # Tajikistan
    473: "YE",  # Yemen
    475: "YE",  # Yemen
    477: "HK",  # Hong Kong
    # Asia-Pacific
    501: "AQ",  # Antarctica (French)
    503: "AU",  # Australia
    506: "MM",  # Myanmar
    508: "BN",  # Brunei
    510: "FM",  # Micronesia
    511: "PW",  # Palau
    512: "NZ",  # New Zealand
    514: "KH",  # Cambodia
    515: "KH",  # Cambodia
    516: "CX",  # Christmas Island
    518: "CK",  # Cook Islands
    520: "FJ",  # Fiji
    523: "CC",  # Cocos Islands
    525: "ID",  # Indonesia
    529: "KI",  # Kiribati
    531: "LA",  # Laos
    533: "MY",  # Malaysia
    536: "MP",  # Northern Mariana Islands
    538: "MH",  # Marshall Islands
    540: "NC",  # New Caledonia
    542: "NU",  # Niue
    544: "NR",  # Nauru
    546: "PF",  # French Polynesia
    548: "PH",  # Philippines
    550: "TL",  # Timor-Leste
    553: "PG",  # Papua New Guinea
    555: "PN",  # Pitcairn Islands
    557: "SB",  # Solomon Islands
    559: "AS",  # American Samoa
    561: "WS",  # Samoa
    563: "SG",  # Singapore
    564: "SG",  # Singapore
    565: "SG",  # Singapore
    566: "SG",  # Singapore
    567: "TH",  # Thailand
    570: "TO",  # Tonga
    572: "TV",  # Tuvalu
    574: "VN",  # Vietnam
    576: "VU",  # Vanuatu
    577: "VU",  # Vanuatu
    578: "WF",  # Wallis and Futuna
    # South America
    601: "ZA",  # South Africa
    603: "AO",  # Angola
    605: "DZ",  # Algeria
    607: "TF",  # French Southern Territories
    608: "IO",  # British Indian Ocean Territory
    609: "BI",  # Burundi
    610: "BJ",  # Benin
    611: "BW",  # Botswana
    612: "CF",  # Central African Republic
    613: "CM",  # Cameroon
    615: "CG",  # Congo (Republic)
    616: "KM",  # Comoros
    617: "CV",  # Cabo Verde
    618: "AQ",  # Antarctica (disputed)
    619: "CI",  # Cote d'Ivoire
    620: "KM",  # Comoros
    621: "DJ",  # Djibouti
    622: "EG",  # Egypt
    624: "ET",  # Ethiopia
    625: "ER",  # Eritrea
    626: "GA",  # Gabon
    627: "GH",  # Ghana
    629: "GM",  # Gambia
    630: "GW",  # Guinea-Bissau
    631: "GQ",  # Equatorial Guinea
    632: "GN",  # Guinea
    633: "BF",  # Burkina Faso
    634: "KE",  # Kenya
    635: "CD",  # Congo (Democratic Republic)
    636: "LR",  # Liberia
    637: "LR",  # Liberia
    638: "SS",  # South Sudan
    642: "LY",  # Libya
    644: "LS",  # Lesotho
    645: "MU",  # Mauritius
    647: "MG",  # Madagascar
    649: "ML",  # Mali
    650: "MZ",  # Mozambique
    654: "MR",  # Mauritania
    655: "MW",  # Malawi
    656: "NE",  # Niger
    657: "NG",  # Nigeria
    659: "NA",  # Namibia
    660: "RE",  # Reunion
    661: "RW",  # Rwanda
    662: "SD",  # Sudan
    663: "SN",  # Senegal
    664: "SC",  # Seychelles
    665: "SH",  # Saint Helena
    666: "SO",  # Somalia
    667: "SL",  # Sierra Leone
    668: "ST",  # Sao Tome and Principe
    669: "SZ",  # Eswatini
    670: "TD",  # Chad
    671: "TG",  # Togo
    672: "TN",  # Tunisia
    674: "TZ",  # Tanzania
    675: "UG",  # Uganda
    676: "CD",  # DR Congo
    677: "TZ",  # Tanzania
    678: "ZM",  # Zambia
    679: "ZW",  # Zimbabwe
    # South America (continued)
    701: "AR",  # Argentina
    710: "BR",  # Brazil
    720: "BO",  # Bolivia
    725: "CL",  # Chile
    730: "CO",  # Colombia
    735: "EC",  # Ecuador
    740: "FK",  # Falkland Islands
    745: "GF",  # French Guiana
    750: "GY",  # Guyana
    755: "PY",  # Paraguay
    760: "PE",  # Peru
    765: "SR",  # Suriname
    770: "UY",  # Uruguay
    775: "VE",  # Venezuela
}

# ---------------------------------------------------------------------------
# Scoring rule IDs — all 14 rules
# ---------------------------------------------------------------------------
GFW_RULE_IDS: list[str] = [
    "gfw_ais_disabling",
    "gfw_encounter",
    "gfw_loitering",
    "gfw_port_visit",
    "gfw_dark_sar",
    "voyage_pattern",
]

REALTIME_RULE_IDS: list[str] = [
    "ais_gap",
    "sts_proximity",
    "destination_spoof",
    "draft_change",
    "flag_hopping",
    "sanctions_match",
    "vessel_age",
    "speed_anomaly",
    "identity_mismatch",
    "flag_of_convenience",
    "ais_spoofing",
    "ownership_risk",
    "insurance_class_risk",
]

# ---------------------------------------------------------------------------
# Shadow-fleet relevant flag countries
# ---------------------------------------------------------------------------
SHADOW_FLEET_FLAGS: frozenset[str] = frozenset({
    "RU",  # Russia
    "PA",  # Panama
    "LR",  # Liberia
    "MH",  # Marshall Islands
    "CM",  # Cameroon
    "IR",  # Iran
    "HK",  # Hong Kong
    "TV",  # Tuvalu
    "KM",  # Comoros
    "PW",  # Palau
    "GA",  # Gabon
    "TZ",  # Tanzania
    "TG",  # Togo
})

# ---------------------------------------------------------------------------
# Known fraudulent registries (separate from SHADOW_FLEET_FLAGS)
# ---------------------------------------------------------------------------
FRAUDULENT_REGISTRY_FLAGS: frozenset[str] = frozenset({
    "CM",  # Cameroon
    "KM",  # Comoros
    "PW",  # Palau
    "GA",  # Gabon
    "TZ",  # Tanzania
    "GM",  # Gambia
    "MW",  # Malawi
    "SL",  # Sierra Leone
})

# ---------------------------------------------------------------------------
# Shadow fleet destination ports (Indian/Chinese/Turkish refinery ports)
# ---------------------------------------------------------------------------
SHADOW_FLEET_DESTINATIONS: frozenset[str] = frozenset({
    "SIKKA", "JAMNAGAR", "PARADIP", "VADINAR", "MUMBAI", "CHENNAI",
    "QINGDAO", "RIZHAO", "DONGYING", "ZHOUSHAN", "NINGBO", "DALIAN",
    "ISKENDERUN", "MERSIN", "ALIAGA", "DORTYOL", "CEYHAN",
})


# ---------------------------------------------------------------------------
# Flag normalization: alpha-3 / country name → alpha-2
# Imported by scoring rules and enrichment writers to ensure consistent
# flag codes across the system.
# ---------------------------------------------------------------------------

# ISO 3166-1 alpha-3 → alpha-2 (comprehensive)
_ALPHA3_TO_ALPHA2: dict[str, str] = {
    "CYP": "CY", "GBR": "GB", "GRC": "GR", "MLT": "MT", "PAN": "PA",
    "LBR": "LR", "MHL": "MH", "NOR": "NO", "SWE": "SE", "DNK": "DK",
    "DEU": "DE", "NLD": "NL", "FRA": "FR", "ESP": "ES", "ITA": "IT",
    "PRT": "PT", "FIN": "FI", "IRL": "IE", "BEL": "BE", "HRV": "HR",
    "ROU": "RO", "BGR": "BG", "POL": "PL", "EST": "EE", "LVA": "LV",
    "LTU": "LT", "SVN": "SI", "TUR": "TR", "RUS": "RU", "UKR": "UA",
    "USA": "US", "CAN": "CA", "BHS": "BS", "BMU": "BM", "BRB": "BB",
    "BLZ": "BZ", "CHN": "CN", "TWN": "TW", "JPN": "JP", "KOR": "KR",
    "SGP": "SG", "HKG": "HK", "IND": "IN", "IDN": "ID", "MYS": "MY",
    "PHL": "PH", "THA": "TH", "VNM": "VN", "AUS": "AU", "NZL": "NZ",
    "BRA": "BR", "ARG": "AR", "CHL": "CL", "COL": "CO", "MEX": "MX",
    "ARE": "AE", "SAU": "SA", "IRN": "IR", "ISR": "IL", "EGY": "EG",
    "ZAF": "ZA", "NGA": "NG", "KEN": "KE", "TZA": "TZ", "GHA": "GH",
    "COM": "KM", "CMR": "CM", "GAB": "GA", "TGO": "TG", "SEN": "SN",
    "ATG": "AG", "VCT": "VC", "KNA": "KN", "DMA": "DM", "GRD": "GD",
    "TTO": "TT", "CRI": "CR", "CUB": "CU", "DOM": "DO", "GTM": "GT",
    "HND": "HN", "NIC": "NI", "SLV": "SV", "JAM": "JM", "GIB": "GI",
    "ISL": "IS", "FRO": "FO", "MCO": "MC", "LUX": "LU", "AND": "AD",
    "MNE": "ME", "ALB": "AL", "GEO": "GE", "PLW": "PW", "TUV": "TV",
    "VUT": "VU", "TON": "TO", "FJI": "FJ", "WSM": "WS", "KIR": "KI",
    "WLF": "WF", "MYT": "YT", "REU": "RE", "GLP": "GP", "MTQ": "MQ",
    "SPM": "PM", "BLM": "BL", "MAF": "MF", "SHN": "SH", "AIA": "AI",
    "MSR": "MS", "CYM": "KY", "TCA": "TC", "VGB": "VG", "VIR": "VI",
    "PRI": "PR", "GUM": "GU", "ASM": "AS", "MNP": "MP", "NCL": "NC",
    "PYF": "PF", "PCN": "PN", "TKL": "TK", "NIU": "NU", "COK": "CK",
    "NFK": "NF", "CCK": "CC", "CXR": "CX", "IOT": "IO", "TLS": "TL",
    "BRN": "BN", "MMR": "MM", "KHM": "KH", "LAO": "LA", "BGD": "BD",
    "LKA": "LK", "MDV": "MV", "NPL": "NP", "BTN": "BT", "MNG": "MN",
    "PRK": "KP", "MAC": "MO", "PSE": "PS", "SYR": "SY", "IRQ": "IQ",
    "JOR": "JO", "LBN": "LB", "KWT": "KW", "BHR": "BH", "QAT": "QA",
    "OMN": "OM", "YEM": "YE", "AFG": "AF", "TKM": "TM", "UZB": "UZ",
    "KGZ": "KG", "TJK": "TJ", "AZE": "AZ", "ARM": "AM", "MDA": "MD",
    "BLR": "BY", "CZE": "CZ", "HUN": "HU", "MKD": "MK", "LIE": "LI",
    "SRB": "RS", "BIH": "BA", "HTI": "HT", "CUW": "CW", "ABW": "AW",
    "SUR": "SR", "GUY": "GY", "ECU": "EC", "PER": "PE", "BOL": "BO",
    "PRY": "PY", "URY": "UY", "VEN": "VE",
    "MAR": "MA", "DZA": "DZ", "TUN": "TN", "LBY": "LY", "SDN": "SD",
    "SSD": "SS", "ERI": "ER", "ETH": "ET", "DJI": "DJ", "SOM": "SO",
    "UGA": "UG", "RWA": "RW", "BDI": "BI", "COD": "CD", "COG": "CG",
    "AGO": "AO", "MOZ": "MZ", "MDG": "MG", "MUS": "MU", "CPV": "CV",
    "GNB": "GW", "GIN": "GN", "SLE": "SL", "GMB": "GM", "MLI": "ML",
    "BFA": "BF", "NER": "NE", "TCD": "TD", "CAF": "CF", "GNQ": "GQ",
    "BWA": "BW", "NAM": "NA", "ZMB": "ZM", "ZWE": "ZW", "MWI": "MW",
    "LSO": "LS", "SWZ": "SZ", "SLB": "SB", "PNG": "PG", "NRU": "NR",
    "FSM": "FM",
}

# Country name → alpha-2
_NAME_TO_ALPHA2: dict[str, str] = {
    "ANTIGUA AND BARBUDA": "AG", "AUSTRALIA": "AU", "BAHAMAS": "BS",
    "BARBADOS": "BB", "BELGIUM": "BE", "BELIZE": "BZ", "BERMUDA": "BM",
    "BRAZIL": "BR", "BULGARIA": "BG", "CAMEROON": "CM", "CANADA": "CA",
    "CHILE": "CL", "CHINA": "CN", "COLOMBIA": "CO", "COMOROS": "KM",
    "COOK ISLANDS": "CK", "COSTA RICA": "CR", "CROATIA": "HR", "CUBA": "CU",
    "CYPRUS": "CY", "DENMARK": "DK", "DOMINICA": "DM",
    "DOMINICAN REPUBLIC": "DO", "ECUADOR": "EC", "EGYPT": "EG",
    "ESTONIA": "EE", "FAROE ISLANDS": "FO", "FIJI": "FJ", "FINLAND": "FI",
    "FRANCE": "FR", "GABON": "GA", "GEORGIA": "GE", "GERMANY": "DE",
    "GHANA": "GH", "GIBRALTAR": "GI", "GREECE": "GR", "GRENADA": "GD",
    "GUATEMALA": "GT", "HONDURAS": "HN", "HONG KONG": "HK", "ICELAND": "IS",
    "INDIA": "IN", "INDONESIA": "ID", "IRAN": "IR", "IRELAND": "IE",
    "ISLE OF MAN": "IM", "ISRAEL": "IL", "ITALY": "IT", "JAMAICA": "JM",
    "JAPAN": "JP", "KENYA": "KE", "KIRIBATI": "KI", "KOREA": "KR",
    "SOUTH KOREA": "KR", "KUWAIT": "KW", "LATVIA": "LV", "LEBANON": "LB",
    "LIBERIA": "LR", "LITHUANIA": "LT", "LUXEMBOURG": "LU", "MALAYSIA": "MY",
    "MALDIVES": "MV", "MALTA": "MT", "MARSHALL ISLANDS": "MH",
    "MAURITIUS": "MU", "MEXICO": "MX", "MONACO": "MC", "MONTENEGRO": "ME",
    "MOROCCO": "MA", "MOZAMBIQUE": "MZ", "MYANMAR": "MM",
    "NETHERLANDS": "NL", "NEW ZEALAND": "NZ", "NICARAGUA": "NI",
    "NIGERIA": "NG", "NORWAY": "NO", "PALAU": "PW", "PANAMA": "PA",
    "PAPUA NEW GUINEA": "PG", "PERU": "PE", "PHILIPPINES": "PH",
    "POLAND": "PL", "PORTUGAL": "PT", "QATAR": "QA", "ROMANIA": "RO",
    "RUSSIA": "RU", "RUSSIAN FEDERATION": "RU", "SAINT KITTS AND NEVIS": "KN",
    "SAINT VINCENT AND THE GRENADINES": "VC", "SAINT VINCENT": "VC",
    "SAMOA": "WS", "SAUDI ARABIA": "SA", "SENEGAL": "SN", "SIERRA LEONE": "SL",
    "SINGAPORE": "SG", "SLOVENIA": "SI", "SOUTH AFRICA": "ZA", "SPAIN": "ES",
    "SRI LANKA": "LK", "SWEDEN": "SE", "SWITZERLAND": "CH", "TAIWAN": "TW",
    "TANZANIA": "TZ", "THAILAND": "TH", "TOGO": "TG", "TONGA": "TO",
    "TRINIDAD AND TOBAGO": "TT", "TUNISIA": "TN", "TURKEY": "TR",
    "TUVALU": "TV", "UKRAINE": "UA", "UNITED ARAB EMIRATES": "AE",
    "UNITED KINGDOM": "GB", "UNITED STATES": "US", "URUGUAY": "UY",
    "VANUATU": "VU", "VENEZUELA": "VE", "VIETNAM": "VN",
    "CAYMAN ISLANDS": "KY", "WALLIS AND FUTUNA": "WF",
    "NORTH KOREA": "KP", "DEMOCRATIC REPUBLIC OF THE CONGO": "CD",
    "REPUBLIC OF THE CONGO": "CG", "IVORY COAST": "CI",
    "COTE D'IVOIRE": "CI", "CABO VERDE": "CV", "CAPE VERDE": "CV",
    "TIMOR-LESTE": "TL", "EAST TIMOR": "TL", "BRUNEI": "BN",
    "HONG KONG SAR": "HK", "MACAU": "MO", "MACAO": "MO",
    "CURACAO": "CW", "ARUBA": "AW", "SURINAME": "SR", "GUYANA": "GY",
    "ALGERIA": "DZ", "LIBYA": "LY", "SUDAN": "SD", "SOUTH SUDAN": "SS",
    "ERITREA": "ER", "ETHIOPIA": "ET", "DJIBOUTI": "DJ", "SOMALIA": "SO",
    "UGANDA": "UG", "RWANDA": "RW", "BURUNDI": "BI", "ANGOLA": "AO",
    "NAMIBIA": "NA", "ZAMBIA": "ZM", "ZIMBABWE": "ZW", "MALAWI": "MW",
    "LESOTHO": "LS", "ESWATINI": "SZ", "SWAZILAND": "SZ",
    "BOTSWANA": "BW", "MADAGASCAR": "MG", "SOLOMON ISLANDS": "SB",
    "EQUATORIAL GUINEA": "GQ", "GUINEA-BISSAU": "GW", "GUINEA": "GN",
    "GAMBIA": "GM", "BURKINA FASO": "BF",
    "GREAT BRITAIN": "GB", "UK": "GB", "ENGLAND": "GB",
    "REPUBLIC OF KOREA": "KR", "IRAN, ISLAMIC REPUBLIC OF": "IR",
    "KOREA, REPUBLIC OF": "KR",
    "KOREA, DEMOCRATIC PEOPLE'S REPUBLIC OF": "KP",
}


def normalize_flag(flag: str | None) -> str | None:
    """Normalize a flag code or country name to ISO alpha-2 uppercase.

    Handles alpha-3 codes (GBR→GB), country names (Cyprus→CY),
    and passes through valid alpha-2 codes unchanged.
    Returns None if input is None/empty.
    """
    if not flag:
        return None
    flag = flag.strip().upper()
    if not flag:
        return None
    if flag in _ALPHA3_TO_ALPHA2:
        return _ALPHA3_TO_ALPHA2[flag]
    if flag in _NAME_TO_ALPHA2:
        return _NAME_TO_ALPHA2[flag]
    return flag
