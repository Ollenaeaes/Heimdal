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
# 5 GFW-sourced + 9 real-time = 14 rules
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
    "speed_anomaly": 15,
    "identity_mismatch": 100,
    "flag_of_convenience": 40,
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
