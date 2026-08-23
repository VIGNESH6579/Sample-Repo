import csv, json, re
from pathlib import Path
from openpyxl import load_workbook


def norm(text):
    text = str(text).upper().replace('&', ' AND ')
    text = re.sub(r'[^A-Z0-9]+', ' ', text)
    stop = {'LIMITED','LTD','INDIA','INDIA LIMITED','THE','COMPANY','CORPORATION','CORP','OF','AND'}
    return {t for t in text.split() if t not in stop}

aliases = {
    'TATA CONSULTANCY SERVICES':'TCS','LARSEN TOUBRO':'LT','MAHINDRA MAHINDRA':'M&M','KOTAK MAHINDRA BANK':'KOTAKBANK',
    'HINDUSTAN AERONAUTICS':'HAL','ETERNAL ZOMATO':'ETERNAL','OIL NATURAL GAS CORPORATION':'ONGC','BHARAT ELECTRONICS':'BEL',
    'POWER GRID CORPORATION':'POWERGRID','AVENUE SUPERMARTS DMART':'DMART','ADANI GREEN ENERGY':'ADANIGREEN','GRASIM INDUSTRIES':'GRASIM',
    'INTERGLOBE AVIATION':'INDIGO','ADANI ENERGY SOLUTIONS':'ADANIENSOL','INDIAN OIL CORPORATION':'IOC','JIO FINANCIAL SERVICES':'JIOFIN',
    'SOLAR INDUSTRIES':'SOLARINDS','SAMVARDHANA MOTHERSON INTERNATIONAL':'MOTHERSON','CHOLAMANDALAM INVESTMENT':'CHOLAFIN','VARUN BEVERAGES':'VBL',
    'HITACHI ENERGY':'POWERINDIA','VODAFONE IDEA':'IDEA','POWER FINANCE CORPORATION':'PFC','BHARAT HEAVY ELECTRICALS':'BHEL',
    'BHARAT PETROLEUM':'BPCL','LODHA DEVELOPERS':'LODHA','CG POWER INDUSTRIAL SOLUTIONS':'CGPOWER','BAJAJ HOLDINGS INVESTMENTS':'BAJAJHLDNG',
    'TATA MOTORS PASSENGER VEHICLES':'TMPV','GODREJ CONSUMER PRODUCTS':'GODREJCP','MAX HEALTHCARE INSTITUTE':'MAXHEALTH','GE VERNOVA T D INDIA':'GVT&D',
    'ADITYA BIRLA CAPITAL':'ABCAPITAL','VEDANTA':'VEDL','ORACLE FINANCIAL SERVICES SOFTWARE':'OFSS','SHREE CEMENT':'SHREECEM',
    'LAURUS LABS':'LAURUSLABS','DR REDDYS LABORATORIES':'DRREDDY','NYKAA FSN E COMMERCE':'NYKAA','MAZAGON DOCK SHIPBUILDERS':'MAZDOCK',
    'DIXON TECHNOLOGIES':'DIXON','ONE 97 COMMUNICATIONS PAYTM':'PAYTM','ICICI LOMBARD GENERAL INSURANCE':'ICICIGI','INFO EDGE':'NAUKRI',
    'SWIGGY':'SWIGGY','AU SMALL FINANCE BANK':'AUBANK','WAAREE ENERGIES':'WAAREEENER',    'NIPPON LIFE INDIA AMC':'NAM_INDIA',

    'PB FINTECH POLICYBAZAAR':'POLICYBZR','ICICI PRUDENTIAL LIFE INSURANCE':'ICICIPRULI','PRESTIGE ESTATES PROJECTS':'PRESTIGE',
    'FORTIS HEALTHCARE':'FORTIS','STEEL AUTHORITY OF INDIA SAIL':'SAIL','PHOENIX MILLS':'PHOENIXLTD','ALKEM LABORATORIES':'ALKEM',
    'GLENMARK PHARMACEUTICALS':'GLENMARK','RADICO KHAITAN':'RADICO','TUBE INVESTMENTS OF INDIA':'TIINDIA','MAX FINANCIAL SERVICES':'MFSL',
    'MOTILAL OSWAL FINANCIAL SERVICES':'MOTILALOFS','VISHAL MEGA MART':'VMM','RAIL VIKAS NIGAM':'RVNL','PREMIER ENERGIES':'PREMIERENE',
    '360 ONE WAM':'360ONE','BHARAT DYNAMICS':'BDL','SONA BLW PRECISION FORGINGS':'SONACOMS','CONTAINER CORPORATION OF INDIA':'CONCOR',
    'COCHIN SHIPYARD':'COCHINSHIP','DELHIVERY':'DELHIVERY','BLUE STAR':'BLUESTARCO','GODFREY PHILLIPS INDIA':'GODFRYPHLP',
    'LIC OF INDIA':'LICI','LIC HOUSING FINANCE':'LICHSGFIN','AMBER ENTERPRISES':'AMBER','KAYNES TECHNOLOGY INDIA':'KAYNES','FORCE MOTORS':'FORCEMOT',
    'KPIT TECHNOLOGIES':'KPITTECH','KFIN TECHNOLOGIES':'KFINTECH','CROMPTON GREAVES CONSUMER ELECTRICALS':'CROMPTON','INDIAN ENERGY EXCHANGE':'IEX',
    'ADANI PORTS SEZ':'ADANIPORTS','DIVIS LABORATORIES':'DIVISLAB','TVS MOTORS':'TVSMOTOR','BAJAJ AUTO':'BAJAJ_AUTO','IRFC':'IRFC','HDFC AMC':'HDFCAMC',
    'MCX':'MCX','NALCO':'NATIONALUM','IREDA':'IREDA','CDSL':'CDSL','CAMS':'CAMS'
}

alias_by_key = {' '.join(sorted(norm(k))): v for k, v in aliases.items()}

wb = load_workbook('/home/ubuntu/upload/NSE_FO_Options_Stocks_List.xlsx', read_only=True, data_only=True)
ws = wb['FO Options Stocks']
workbook = [str(row[1]).strip() for row in ws.iter_rows(min_row=2, values_only=True) if row[1] and 'LTIM' not in str(row[1]).upper()]
with open('/tmp/EQUITY_L.csv', newline='', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    rows = [{(k or '').strip(): (v or '').strip() for k, v in row.items()} for row in reader]
by_norm = {frozenset(norm(r['NAME OF COMPANY'])): r['SYMBOL'] for r in rows if r.get('SERIES') == 'EQ'}
output = []
unresolved = []
for name in workbook:
    key = ' '.join(sorted(norm(name)))
    ticker = alias_by_key.get(key)
    if not ticker:
        ticker = by_norm.get(frozenset(norm(name)))
    if not ticker:
        matches = [symbol for k, symbol in by_norm.items() if norm(name) <= set(k) or set(k) <= norm(name)]
        ticker = matches[0] if matches else None
    if not ticker:
        unresolved.append(name)
    output.append({'name': name, 'ticker': ticker})
Path('data/universe.json').write_text(json.dumps({'source':'NSE_FO_Options_Stocks_List.xlsx','excluded':['LTIMindtree'],'stocks':output,'unresolved':unresolved}, indent=2) + '\n')
print('TOTAL', len(output), 'UNRESOLVED', len(unresolved))
for name in unresolved: print('UNRESOLVED', name)
