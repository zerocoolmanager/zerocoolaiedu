from __future__ import annotations
import hashlib, os, sqlite3
from datetime import datetime, timedelta
from pathlib import Path

APP_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ZeroCoolAI'
DB_PATH = APP_DIR / 'education_history.db'

RESULT_COLS = {'수료여부','수료일','구분','교육종류','교육장소','예약조회내용','수료조회내용','최종조회일시'}
PII_COLS = {'주민등록번호','주민번호','주민번호 앞자리','주민번호 뒷자리','주민등록번호 앞자리','주민등록번호 뒷자리','휴대폰번호','휴대전화','전화번호','휴대폰번호1','휴대폰번호2','휴대폰번호3','휴대폰1','휴대폰2','휴대폰3'}

def connect():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    con=sqlite3.connect(DB_PATH)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA synchronous=NORMAL')
    con.execute('''CREATE TABLE IF NOT EXISTS person_state(
      person_key TEXT PRIMARY KEY, name TEXT, company TEXT,
      last_seen_at TEXT, last_seen_fingerprint TEXT,
      last_queried_at TEXT, last_queried_fingerprint TEXT,
      completion_status TEXT, reservation_date TEXT, site TEXT, method TEXT)''')
    con.execute('''CREATE TABLE IF NOT EXISTS education_history(
      id INTEGER PRIMARY KEY AUTOINCREMENT, checked_at TEXT, person_key TEXT,
      company TEXT, name TEXT, site TEXT, reservation_date TEXT, method TEXT,
      reservation_status TEXT, completion_status TEXT, completion_date TEXT,
      category TEXT, course TEXT, place TEXT, detail TEXT)''')
    return con

def person_key(name, resident='', phone=''):
    raw=(resident or '').strip() or ((name or '').strip()+'|'+(phone or '')[-4:])
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]

def _norm_value(v):
    if v is None:
        return ''
    s=str(v).strip()
    if s.lower() in ('nan','nat','none'):
        return ''
    # 엑셀 날짜/숫자 표기 차이로 동일 정보가 변경으로 오인되지 않도록 정규화
    s=s.replace('.0','') if s.endswith('.0') and s[:-2].isdigit() else s
    return ' '.join(s.split())

def _first_value(row, names):
    cols={str(c).replace(' ',''):c for c in row.index}
    for name in names:
        key=name.replace(' ','')
        if key in cols:
            return _norm_value(row.get(cols[key],''))
    return ''

def row_fingerprint(row):
    """예약 확인에 실제로 영향을 주는 입력정보만 비교한다.

    결과열, 빈 보조열, 엑셀 서식 차이는 제외하여 같은 예약 명단을
    '정보변경'으로 잘못 판정하지 않는다.
    """
    fields={
        'company': _first_value(row,['소속(회사명)','회사명','소속','회사']),
        'name': _first_value(row,['이름','성명']),
        'resident': _first_value(row,['주민등록번호','주민번호']),
        'resident_front': _first_value(row,['주민번호 앞자리','주민등록번호 앞자리']),
        'resident_back': _first_value(row,['주민번호 뒷자리','주민등록번호 뒷자리']),
        'phone': _first_value(row,['휴대폰번호','휴대전화','전화번호']),
        'phone1': _first_value(row,['휴대폰번호1','휴대폰1']),
        'phone2': _first_value(row,['휴대폰번호2','휴대폰2']),
        'phone3': _first_value(row,['휴대폰번호3','휴대폰3']),
        'reservation_date': _first_value(row,['교육시청일','예약일','교육일','시청일']),
        'region': _first_value(row,['사이트','조회사이트','교육사이트','교육기관','연수원','지역']),
        'course': _first_value(row,['교육종류','교육과정','과정명','교육명']),
        'method': _first_value(row,['교육방식','교육방법','방식']),
    }
    raw='\n'.join(f'{k}={fields[k]}' for k in sorted(fields))
    return 'v2:'+hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]

def get_state(key):
    with connect() as con:
        r=con.execute('SELECT last_queried_fingerprint,completion_status,reservation_date,site,method,last_queried_at FROM person_state WHERE person_key=?',(key,)).fetchone()
    return r

def note_seen(key,name,company,fingerprint):
    now=datetime.now().isoformat(timespec='seconds')
    with connect() as con:
        con.execute('''INSERT INTO person_state(person_key,name,company,last_seen_at,last_seen_fingerprint)
        VALUES(?,?,?,?,?) ON CONFLICT(person_key) DO UPDATE SET name=excluded.name,company=excluded.company,last_seen_at=excluded.last_seen_at,last_seen_fingerprint=excluded.last_seen_fingerprint''',(key,name,company,now,fingerprint))

def save_query(person,res,comp,fingerprint):
    key=person_key(person.name,person.resident,person.phone); now=datetime.now().isoformat(timespec='seconds')
    with connect() as con:
        con.execute('''INSERT INTO person_state(person_key,name,company,last_seen_at,last_seen_fingerprint,last_queried_at,last_queried_fingerprint,completion_status,reservation_date,site,method)
        VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(person_key) DO UPDATE SET name=excluded.name,company=excluded.company,last_seen_at=excluded.last_seen_at,last_seen_fingerprint=excluded.last_seen_fingerprint,last_queried_at=excluded.last_queried_at,last_queried_fingerprint=excluded.last_queried_fingerprint,completion_status=excluded.completion_status,reservation_date=excluded.reservation_date,site=excluded.site,method=excluded.method''',
        (key,person.name,person.company,now,fingerprint,now,fingerprint,comp.status,res.reservation_date,res.site,res.method))
        con.execute('''INSERT INTO education_history(checked_at,person_key,company,name,site,reservation_date,method,reservation_status,completion_status,completion_date,category,course,place,detail)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(now,key,person.company,person.name,res.site,res.reservation_date,res.method,res.status,comp.status,comp.completion_date,comp.category,comp.course or res.course,comp.place or res.place,(res.detail+'\n'+comp.detail)[:2000]))

def db_size_text():
    if not DB_PATH.exists(): return '0 KB'
    n=DB_PATH.stat().st_size
    return f'{n/1024:.1f} KB' if n<1024*1024 else f'{n/1024/1024:.2f} MB'

def delete_history_ids(ids):
    if not ids:return
    with connect() as con:
        con.executemany('DELETE FROM education_history WHERE id=?',[(int(x),) for x in ids])

def delete_older_than(days=730):
    cutoff=(datetime.now()-timedelta(days=days)).isoformat(timespec='seconds')
    with connect() as con:
        con.execute('DELETE FROM education_history WHERE checked_at<?',(cutoff,))

def delete_all_history():
    with connect() as con:
        con.execute('DELETE FROM education_history'); con.execute('DELETE FROM person_state')

def compact():
    with connect() as con: con.execute('VACUUM')
