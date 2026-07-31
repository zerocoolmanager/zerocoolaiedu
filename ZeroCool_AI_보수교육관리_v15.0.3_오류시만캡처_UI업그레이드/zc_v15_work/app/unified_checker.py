from __future__ import annotations
import argparse, atexit, json, os, re, shutil, sqlite3, sys, tempfile, time, traceback, zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Optional
import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException, InvalidSessionIdException, NoSuchWindowException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

for s in ('stdout','stderr'):
    obj=getattr(sys,s,None)
    if obj is not None and hasattr(obj,'reconfigure'):
        try: obj.reconfigure(encoding='utf-8',errors='replace')
        except Exception: pass

URLS={
 '서울예약':'https://edu.tredu.kr/',
 '서울수료':'https://seoulttc.or.kr/front/result_list.php',
 '경기예약':'https://yeyak.kytti.or.kr/www/resv/education/reservation/check.do?key=232',
 '경기수료':'https://yeyak.kytti.or.kr/www/resv/education/completion/check.do?key=84',
 '인천예약':'https://www.int.or.kr/transp/transp_freight_confirmation_all.php',
 '인천수료':'https://www.int.or.kr/transp/transp_edu_individual.php',
}
from history_store import person_key, row_fingerprint, get_state, note_seen, save_query

OUT_COLS=['예약일','교육방식','사이트','예약상태','수료여부','수료일','구분','교육종류','교육장소','예약조회내용','수료조회내용','최종조회일시']
APP_VERSION='15.0.10'
SEOUL_ONLINE_SCHEDULE_2026={1:'2026-07-26',2:'2026-07-27',3:'2026-08-10',4:'2026-08-11'}

REGION_COLUMN_NAMES=[
    '사이트','조회사이트','조회 사이트','교육사이트','교육 사이트','연수원','교육기관','교육 기관','지역','소속지역','소속 지역'
]

def normalize_region(value):
    v=text(value).replace(' ','').lower()
    if not v:
        return ''
    if any(k in v for k in ('서울','tredu','seoulttc')):
        return '서울'
    if any(k in v for k in ('경기','kytti','경기도')):
        return '경기'
    if any(k in v for k in ('인천','int.or.kr','인천교통연수원')):
        return '인천'
    return ''

def region_for_person(row,p,allowed_regions):
    # 1순위: 행에 명시된 사이트/교육기관/지역
    for col in REGION_COLUMN_NAMES:
        if col in row.index:
            r=normalize_region(row.get(col,''))
            if r:
                return r if r in allowed_regions else ''
    # 2순위: 소속/회사명에 서울·경기·인천이 명시된 경우
    for value in (p.company, _first_row_text(row,['소속','소속(회사명)','회사명','법인','지사'])):
        r=normalize_region(value)
        if r:
            return r if r in allowed_regions else ''
    # 한 기관만 체크한 경우에는 그 기관을 기본값으로 사용
    if len(allowed_regions)==1:
        return allowed_regions[0]
    # 양쪽이 모두 허용되어도 사람별 소속이 불명확하면 양쪽 조회 금지
    return ''

def _switch_to_new_window(d, old_handles):
    """새 창이 열렸으면 새 창으로 전환한다."""
    try:
        WebDriverWait(d,8).until(lambda x: len(x.window_handles)>len(old_handles))
        new_handles=[h for h in d.window_handles if h not in old_handles]
        if new_handles:
            d.switch_to.window(new_handles[-1])
            return True
    except Exception:
        pass
    return False

def _identity_input_ready(d):
    """현재 문서에 성명/주민번호 입력 화면이 실제로 나타났는지 확인한다."""
    try:
        body=(d.find_element(By.TAG_NAME,'body').text or '')
    except Exception:
        body=''
    visible=[e for e in vis_inputs(d) if (e.get_attribute('type') or 'text').lower() in {'text','tel','number','password'}]
    attrs_text=' '.join(attrs(e) for e in visible)
    has_name=('성명' in body or '이름' in body or '실명' in body or 'name' in attrs_text)
    has_resident=('주민' in body or '생년월일' in body or '앞자리' in body or '뒷자리' in body or 'jumin' in attrs_text)
    return len(visible)>=2 and has_name and has_resident

def _candidate_click_text(e):
    return ' '.join(filter(None, [
        (e.text or '').strip(),
        (e.get_attribute('value') or '').strip(),
        (e.get_attribute('title') or '').strip(),
        (e.get_attribute('aria-label') or '').strip(),
    ])).strip()

def _find_exact_reservation_button(d, labels):
    """서울 첫 화면의 예약확인 카드를 찾는다.
    실제 사이트는 글자 요소와 클릭 이벤트가 걸린 부모 요소가 분리될 수 있어
    텍스트 요소부터 부모 카드까지 모두 후보로 반환한다.
    """
    normalized={re.sub(r'\s+','',x) for x in labels}
    d.switch_to.default_content()
    contexts=[None]
    try:
        frames=[f for f in d.find_elements(By.CSS_SELECTOR,'iframe,frame') if f.is_displayed()]
        # edu.tredu.kr 예약확인은 main 프레임을 우선 사용한다.
        frames.sort(key=lambda f: 0 if ((f.get_attribute('name') or f.get_attribute('id') or '').lower()=='main') else 1)
        contexts += frames
    except Exception:
        pass
    for frame in contexts:
        try:
            d.switch_to.default_content()
            if frame is not None:
                d.switch_to.frame(frame)
            # 1) 일반 클릭 요소
            candidates=d.find_elements(By.XPATH,"//a|//button|//input[@type='button' or @type='submit']|//*[@role='button']|//*[@onclick]")
            ranked=[]
            for e in candidates:
                try:
                    if not e.is_displayed(): continue
                    txt=_candidate_click_text(e)
                    compact=re.sub(r'\s+','',txt)
                    if compact in normalized: rank=0
                    elif any(x in compact for x in normalized): rank=1
                    else: continue
                    ranked.append((rank,len(compact),e,txt))
                except Exception: continue
            if ranked:
                ranked.sort(key=lambda x:(x[0],x[1]))
                return ranked[0][2], frame

            # 2) 텍스트가 들어 있는 일반 요소를 찾고 클릭 가능한 부모까지 올라간다.
            all_nodes=d.find_elements(By.XPATH,"//*[normalize-space(.)!='']")
            text_hits=[]
            for e in all_nodes:
                try:
                    if not e.is_displayed(): continue
                    txt=(e.text or '').strip()
                    compact=re.sub(r'\s+','',txt)
                    if compact in normalized:
                        text_hits.append((0,len(compact),e))
                    elif any(x in compact for x in normalized) and len(compact) < 80:
                        text_hits.append((1,len(compact),e))
                except Exception: continue
            text_hits.sort(key=lambda x:(x[0],x[1]))
            for _,_,leaf in text_hits[:10]:
                cur=leaf
                for _up in range(7):
                    try:
                        tag=(cur.tag_name or '').lower()
                        role=(cur.get_attribute('role') or '').lower()
                        onclick=cur.get_attribute('onclick') or ''
                        href=cur.get_attribute('href') or ''
                        style=(cur.get_attribute('style') or '').lower()
                        cls=(cur.get_attribute('class') or '').lower()
                        if tag in ('a','button') or role=='button' or onclick or href or 'cursor: pointer' in style or 'btn' in cls or 'menu' in cls:
                            return cur, frame
                        cur=cur.find_element(By.XPATH,'..')
                    except Exception:
                        break
                # 클릭 가능한 부모를 못 찾아도 텍스트 요소 자체를 반환한다.
                return leaf, frame
        except Exception:
            continue
    d.switch_to.default_content()
    return None, None

def _context_has_identity(d):
    """현재 문서 또는 main 프레임 안에 본인확인 입력칸이 열렸는지 확인한다."""
    try:
        if _identity_input_ready(d):
            return True
    except Exception:
        pass
    try:
        d.switch_to.default_content()
        frames=d.find_elements(By.CSS_SELECTOR,'iframe,frame')
        frames.sort(key=lambda f: 0 if ((f.get_attribute('name') or f.get_attribute('id') or '').lower()=='main') else 1)
        for f in frames:
            try:
                d.switch_to.default_content(); d.switch_to.frame(f)
                if _identity_input_ready(d):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    try:d.switch_to.default_content()
    except Exception:pass
    return False


def _wait_seoul_button_result(d, old_url, old_handles, seconds=4):
    """클릭이 실제로 반영됐는지 확인한다. 단순 click() 성공만으로는 성공 처리하지 않는다."""
    end=time.time()+seconds
    while time.time()<end:
        try:
            if len(d.window_handles)>len(old_handles):
                _switch_to_new_window(d,old_handles)
            if _context_has_identity(d):
                return True
            if d.current_url!=old_url:
                try:d.switch_to.default_content()
                except Exception:pass
                if _context_has_identity(d):
                    return True
        except (InvalidSessionIdException,NoSuchWindowException):
            raise
        except Exception:
            pass
        time.sleep(.25)
    return False


def click_seoul_reservation_change(d, debug=None, prefix='seoul'):
    """edu.tredu.kr의 main 프레임에서 '교육 예약확인 및 변경'을 반드시 누른다."""
    from selenium.webdriver.common.action_chains import ActionChains
    labels=('교육 예약확인 및 변경','예약확인 및 변경','예약 확인 및 변경')
    normalized={re.sub(r'\s+','',x) for x in labels}
    debug=Path(debug) if debug else Path.cwd()/'debug'
    old_url=d.current_url
    old_handles=list(d.window_handles)

    # 사이트 구조상 main 프레임이 핵심이므로 이름으로 먼저 직접 진입한다.
    contexts=[]
    try:
        d.switch_to.default_content()
        main=d.find_elements(By.CSS_SELECTOR,"iframe[name='main'],frame[name='main'],iframe#main,frame#main")
        contexts.extend(main)
        others=[f for f in d.find_elements(By.CSS_SELECTOR,'iframe,frame') if f not in contexts]
        contexts.extend(others)
    except Exception:
        contexts=[]
    contexts.append(None)

    candidates=[]
    for frame in contexts:
        try:
            d.switch_to.default_content()
            if frame is not None:
                d.switch_to.frame(frame)
            nodes=d.find_elements(By.XPATH,"//a|//button|//input[@type='button' or @type='submit']|//*[@role='button']|//*[@onclick]|//*[normalize-space(.)!='']")
            for e in nodes:
                try:
                    if not e.is_displayed():continue
                    raw=' '.join(filter(None,[(e.text or '').strip(),(e.get_attribute('value') or '').strip(),(e.get_attribute('title') or '').strip(),(e.get_attribute('aria-label') or '').strip()]))
                    compact=re.sub(r'\s+','',raw)
                    if compact in normalized or any(x in compact for x in normalized):
                        cur=e
                        chain=[]
                        for _ in range(8):
                            if cur not in chain:chain.append(cur)
                            try:cur=cur.find_element(By.XPATH,'..')
                            except Exception:break
                        for target in chain:
                            try:
                                tag=(target.tag_name or '').lower(); cls=(target.get_attribute('class') or '').lower()
                                onclick=target.get_attribute('onclick') or ''; href=target.get_attribute('href') or ''
                                priority=0 if tag in ('a','button') or onclick or href or 'btn' in cls or 'menu' in cls or 'card' in cls else 1
                                candidates.append((priority,len(compact),frame,target,raw))
                            except Exception:pass
                except Exception:continue
        except Exception:continue

    # 중복 WebElement 제거
    uniq=[]; seen=set()
    for item in sorted(candidates,key=lambda x:(x[0],x[1])):
        try:key=item[3].id
        except Exception:key=id(item[3])
        if key in seen:continue
        seen.add(key);uniq.append(item)

    if not uniq:
        dump_debug(d,debug,f'{prefix}_버튼없음')
        raise RuntimeError("서울 main 프레임에서 '교육 예약확인 및 변경' 버튼을 찾지 못했습니다.")

    last_error=None
    for _,_,frame,target,button_text in uniq[:20]:
        try:
            d.switch_to.default_content()
            if frame is not None:d.switch_to.frame(frame)
            d.execute_script("arguments[0].scrollIntoView({block:'center',inline:'center'});",target)
            time.sleep(.2)
            href=target.get_attribute('href') or ''
            onclick=target.get_attribute('onclick') or ''
            attempts=[
                ('일반클릭',lambda:target.click()),
                ('액션클릭',lambda:ActionChains(d).move_to_element(target).pause(.2).click().perform()),
                ('JS클릭',lambda:d.execute_script('arguments[0].click();',target)),
                ('이벤트클릭',lambda:d.execute_script("arguments[0].dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));arguments[0].dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));arguments[0].dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}));",target)),
            ]
            if onclick:
                attempts.append(('onclick실행',lambda:d.execute_script(onclick)))
            for method,fn in attempts:
                try:
                    fn()
                    print(f'STEP|서울예약|교육 예약확인 및 변경 클릭시도|{method}|{button_text}',flush=True)
                    if _wait_seoul_button_result(d,old_url,old_handles,4):
                        print(f'STEP|서울예약|교육 예약확인 및 변경 클릭완료|{method}',flush=True)
                        return True
                except Exception as exc:
                    last_error=exc
            if href and not href.lower().startswith('javascript:'):
                try:
                    d.switch_to.default_content();d.get(href)
                    if _wait_seoul_button_result(d,old_url,old_handles,6):
                        print('STEP|서울예약|교육 예약확인 및 변경 클릭완료|href이동',flush=True)
                        return True
                except Exception as exc:last_error=exc
        except Exception as exc:
            last_error=exc
            continue

    dump_debug(d,debug,f'{prefix}_버튼클릭후_입력화면없음')
    detail=f' ({type(last_error).__name__}: {last_error})' if last_error else ''
    raise RuntimeError("'교육 예약확인 및 변경' 버튼을 실제로 눌렀지만 성명·주민번호 입력화면이 열리지 않았습니다."+detail)

@dataclass
class Person:
    row:int; company:str; name:str; resident:str; phone:str; requested_date:str=''
@dataclass
class ReservationResult:
    found:bool=False; site:str=''; reservation_date:str=''; method:str=''; status:str=''; course:str=''; place:str=''; detail:str=''; error:str=''
@dataclass
class CompletionResult:
    status:str=''; completion_date:str=''; category:str=''; course:str=''; place:str=''; detail:str=''; error:str=''

def clean_digits(v):
    if pd.isna(v) or v is None: return ''
    return re.sub(r'\D','',str(v))
def fixed_digit_segment(value,width):
    """Restore leading zeroes lost when Excel reads a digit segment as numeric."""
    digits=clean_digits(value)
    if not digits:return ''
    return digits[-width:].zfill(width)
def normalized_phone(full='',part1='',part2='',part3=''):
    digits=clean_digits(full)
    if digits:
        if len(digits)==10 and digits.startswith('10'):digits='0'+digits
        return digits[:11]
    return (
        fixed_digit_segment(part1,3)+
        fixed_digit_segment(part2,4)+
        fixed_digit_segment(part3,4)
    )
def text(v): return '' if pd.isna(v) or v is None else str(v).strip()
def normalize_date(v, year=None):
    if v is None or pd.isna(v): return ''
    if isinstance(v,(datetime,pd.Timestamp)): return v.strftime('%Y-%m-%d')
    s=str(v).strip(); y=year or datetime.now().year
    pats=[r'(20\d{2})[./-](\d{1,2})[./-](\d{1,2})',r'(\d{1,2})[./-](\d{1,2})',r'(\d{1,2})\s*월\s*(\d{1,2})\s*일']
    m=re.search(pats[0],s)
    if m:
        try:return date(int(m.group(1)),int(m.group(2)),int(m.group(3))).isoformat()
        except:return ''
    for p in pats[1:]:
        m=re.search(p,s)
        if m:
            try:return date(y,int(m.group(1)),int(m.group(2))).isoformat()
            except:return ''
    return ''
def date_obj(s):
    try:return datetime.strptime(s[:10],'%Y-%m-%d').date()
    except:return None

def sanitize_xlsx(path:Path)->Path:
    if path.suffix.lower()!='.xlsx': return path
    try:
        with zipfile.ZipFile(path,'r') as z:
            if 'docProps/custom.xml' not in z.namelist(): return path
            root=ET.fromstring(z.read('docProps/custom.xml'))
            bad=[c for c in list(root) if c.tag.endswith('property') and not c.attrib.get('name')]
            if not bad:return path
            for c in bad:root.remove(c)
            d=Path(tempfile.mkdtemp(prefix='zc_xlsx_')); atexit.register(lambda:shutil.rmtree(d,ignore_errors=True)); out=d/path.name
            with zipfile.ZipFile(path,'r') as src,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as dst:
                for item in src.infolist():
                    dst.writestr(item,ET.tostring(root,encoding='utf-8',xml_declaration=True) if item.filename=='docProps/custom.xml' else src.read(item.filename))
            return out
    except:return path

def clean_saved_xlsx(path:Path)->None:
    """Excel/COM이 이름 없는 사용자 지정 속성을 남긴 경우 결과파일을 제자리에서 정리한다."""
    if path.suffix.lower()!='.xlsx' or not path.exists():
        return
    try:
        with zipfile.ZipFile(path,'r') as src:
            if 'docProps/custom.xml' not in src.namelist():
                return
            root=ET.fromstring(src.read('docProps/custom.xml'))
            bad=[c for c in list(root) if c.tag.endswith('property') and not c.attrib.get('name')]
            if not bad:
                return
            for c in bad:
                root.remove(c)
            tmp=path.with_suffix(path.suffix+'.cleaning')
            with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as dst:
                for item in src.infolist():
                    data=(ET.tostring(root,encoding='utf-8',xml_declaration=True)
                          if item.filename=='docProps/custom.xml' else src.read(item.filename))
                    dst.writestr(item,data)
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass

def read_input(path:Path):
    eng='xlrd' if path.suffix.lower()=='.xls' else 'openpyxl'; p=sanitize_xlsx(path)
    sheets=pd.read_excel(p,sheet_name=None,header=None,engine=eng)
    keys={'이름','성명'}
    for sn,raw in sheets.items():
        for h in range(min(30,len(raw))):
            vals=[text(x) for x in raw.iloc[h].tolist()]
            if any(v in keys for v in vals) and any('주민번호' in v for v in vals):
                df=pd.read_excel(p,sheet_name=sn,header=h,engine=eng)
                df.columns=[text(c) for c in df.columns]
                return sn,h,df
    raise ValueError('이름과 주민번호 열이 있는 제목행을 찾지 못했습니다.')

def findcol(df,names,contains=False):
    for n in names:
        for c in df.columns:
            if (n in c if contains else c==n):return c
    return None

def people_from_df(df):
    namec=findcol(df,['이름','성명']); comp=findcol(df,['소속(회사명)','회사명','소속'])
    front=findcol(df,['주민번호 앞자리','주민등록번호 앞자리']); back=findcol(df,['주민번호 뒷자리','주민등록번호 뒷자리'])
    full=findcol(df,['주민등록번호','주민번호'])
    p1=findcol(df,['휴대폰번호1','휴대폰1']);p2=findcol(df,['휴대폰번호2','휴대폰2']);p3=findcol(df,['휴대폰번호3','휴대폰3']); phonefull=findcol(df,['휴대폰번호','휴대전화','전화번호'])
    req=findcol(df,['교육시청일','예약일','교육일','시청일'])
    out=[]
    for i,row in df.iterrows():
        name=text(row.get(namec,''));
        if not name:continue
        resident=(clean_digits(row.get(full,'')) if full else
                  fixed_digit_segment(row.get(front,''),6)+fixed_digit_segment(row.get(back,''),7))
        phone=normalized_phone(
            row.get(phonefull,'') if phonefull else '',
            row.get(p1,'') if p1 else '',
            row.get(p2,'') if p2 else '',
            row.get(p3,'') if p3 else '',
        )
        out.append(Person(i,text(row.get(comp,'')),name,resident[:13],phone[:11],normalize_date(row.get(req,''))))
    return out

BROWSER_MODE='hidden'

def driver_new(headless=False):
    active_mode=BROWSER_MODE
    def make_options(mode):
        o=webdriver.ChromeOptions()
        args=['--disable-blink-features=AutomationControlled','--disable-dev-shm-usage','--no-sandbox','--lang=ko-KR']
        if mode=='hidden':
            args += ['--headless=new','--disable-gpu','--window-size=1365,900']
        elif mode=='background':
            args += ['--window-size=560,700','--window-position=20,45']
        else:
            # Visible mode must never inherit Chrome's previous maximized state.
            args += ['--window-size=560,700','--window-position=20,45']
        for a in args:o.add_argument(a)
        o.add_experimental_option('excludeSwitches',['enable-automation'])
        return o
    try:
        d=webdriver.Chrome(options=make_options(BROWSER_MODE))
    except Exception as e:
        if BROWSER_MODE!='hidden':
            raise RuntimeError(f'Chrome 실행 실패: Google Chrome 설치와 인터넷 연결을 확인하세요. {type(e).__name__}: {e}') from e
        print(f'BROWSER|완전 숨김 실행 실패 · 좌측 상단 작은 창으로 자동 전환 · {type(e).__name__}',flush=True)
        try:
            d=webdriver.Chrome(options=make_options('background'))
            active_mode='background'
        except Exception as fallback_error:
            raise RuntimeError(f'Chrome 실행 실패: Google Chrome 설치와 인터넷 연결을 확인하세요. {type(fallback_error).__name__}: {fallback_error}') from fallback_error
    d.set_page_load_timeout(45)
    if active_mode=='hidden':
        print('BROWSER|완전 숨김 모드로 실행', flush=True)
    elif active_mode in ('background','normal'):
        try:
            # 듀얼 모니터 경계를 넘어가지 않도록 주 화면 좌측 상단 고정 좌표를 사용한다.
            import ctypes
            sh=ctypes.windll.user32.GetSystemMetrics(1)
            width=560; height=max(540,min(700,sh-90))
            d.set_window_rect(x=20,y=45,width=width,height=height)
        except Exception:
            try:
                d.set_window_size(560,700)
                d.set_window_position(20,45)
            except Exception:
                pass
        print('BROWSER|좌측 상단 작은 창 모드로 실행', flush=True)
    return d

def driver_alive(d):
    try:
        _=d.current_url
        _=d.window_handles
        return True
    except Exception:
        return False

def driver_close(d):
    if d is None:return
    try:d.quit()
    except Exception:pass

def ensure_driver(d,headless=False):
    if driver_alive(d):
        return d,False
    driver_close(d)
    nd=driver_new(headless)
    print('SESSION|Chrome 세션 재생성',flush=True)
    return nd,True

def vis_inputs(d):return [x for x in d.find_elements(By.CSS_SELECTOR,'input') if x.is_displayed() and x.is_enabled()]
def attrs(e):return ' '.join((e.get_attribute(k) or '') for k in ['name','id','placeholder','title','aria-label','alt']).lower()
def score(e,words):return sum(10 for w in words if w.lower() in attrs(e))
def fill(e,v):e.click();e.clear();e.send_keys(v)
def input_by_name(d,*names):
    """Find a visible input by exact name/id, excluding unrelated site search."""
    wanted={str(x).strip().lower() for x in names if str(x).strip()}
    for e in d.find_elements(By.CSS_SELECTOR,'input'):
        try:
            key=(e.get_attribute('name') or e.get_attribute('id') or '').strip().lower()
            if key in wanted and e.is_displayed() and e.is_enabled():
                return e
        except Exception:
            continue
    return None
def click_consent(d):
    clicked=False
    for e in d.find_elements(By.CSS_SELECTOR,"input[type='checkbox']"):
        if e.is_displayed() and e.is_enabled() and not e.is_selected():
            try:
                d.execute_script('arguments[0].click();',e)
                clicked=True
            except:pass
    return clicked

def set_required_consents(d, region, mode, *field_ids):
    """Select only the consent fields required by the current site/form.

    Some sites hide the native checkbox and expose a styled label.  Selenium's
    displayed-only click therefore misses it.  Setting the checked property
    and emitting input/change events satisfies the form without opening the
    site's 'full text' modal.
    """
    selected=[]
    for field_id in field_ids:
        candidates=d.find_elements(
            By.CSS_SELECTOR,
            f"input#{field_id},input[name='{field_id}']",
        )
        target=next((e for e in candidates if e.is_enabled()),None)
        if target is None:
            raise RuntimeError(f'{region} {mode} 필수 동의항목({field_id})을 찾지 못했습니다.')
        d.execute_script("""
            const e=arguments[0];
            e.checked=true;
            e.setAttribute('checked','checked');
            e.dispatchEvent(new Event('input',{bubbles:true}));
            e.dispatchEvent(new Event('change',{bubbles:true}));
        """,target)
        if not target.is_selected():
            raise RuntimeError(f'{region} {mode} 필수 동의항목({field_id}) 선택에 실패했습니다.')
        selected.append(field_id)
    print(f'CONSENT|{region}|{mode}|{"+".join(selected) if selected else "동의절차없음"}|완료',flush=True)
    return True

def close_seoul_consent_popup(d, timeout=5):
    """서울 예약조회에서 개인정보 동의 직후 뜨는 안내 팝업만 닫는다.

    자바스크립트 alert와 화면 내 모달의 '닫기' 버튼을 모두 지원한다.
    팝업이 없으면 오류로 처리하지 않고 바로 다음 단계로 진행한다.
    """
    end=time.time()+timeout
    while time.time()<end:
        # 1) 브라우저 자바스크립트 alert/confirm
        try:
            alert=d.switch_to.alert
            _=alert.text
            alert.accept()
            time.sleep(.4)
            return True
        except Exception:
            pass

        # 2) 화면 내 레이어/모달의 닫기 버튼
        xpaths=[
            "//*[self::button or self::a or self::input][normalize-space(string(.))='닫기' or @value='닫기' or @title='닫기']",
            "//*[contains(@class,'modal') or contains(@class,'popup') or contains(@class,'layer')]//*[self::button or self::a or self::input][contains(normalize-space(string(.)),'닫기') or contains(@value,'닫기')]",
        ]
        for xp in xpaths:
            for e in d.find_elements(By.XPATH,xp):
                try:
                    if e.is_displayed() and e.is_enabled():
                        d.execute_script('arguments[0].click();',e)
                        time.sleep(.4)
                        return True
                except Exception:
                    pass
        time.sleep(.2)
    return False

def submit(d):
    """현재 본문/iframe에서 조회 버튼을 안정적으로 누른다.

    사이트별로 버튼이 input, 이미지, onclick 링크, 폼 submit 등으로 달라질 수 있어
    텍스트 후보 클릭 후 requestSubmit/form.submit 순서로 보완한다.
    """
    keywords=('예약확인','예약조회','조회하기','본인인증','실명인증','확인','조회','검색','인증','다음')
    try:d.switch_to.default_content()
    except Exception:pass
    contexts=[None]
    try:contexts += [f for f in d.find_elements(By.CSS_SELECTOR,'iframe,frame') if f.is_displayed()]
    except Exception:pass
    for frame in contexts:
        try:
            d.switch_to.default_content()
            if frame is not None:d.switch_to.frame(frame)
            candidates=d.find_elements(By.CSS_SELECTOR,"button,input[type='submit'],input[type='button'],a,[role='button'],[onclick]")
            ranked=[]
            for e in candidates:
                try:
                    if not e.is_displayed() or not e.is_enabled():continue
                    raw=' '.join(filter(None,[(e.text or '').strip(),(e.get_attribute('value') or '').strip(),(e.get_attribute('title') or '').strip(),(e.get_attribute('aria-label') or '').strip(),(e.get_attribute('alt') or '').strip()]))
                    compact=re.sub(r'\s+','',raw)
                    hits=[k for k in keywords if k in compact]
                    typ=(e.get_attribute('type') or '').lower()
                    if hits:
                        ranked.append((0 if compact in keywords else 1,len(compact),e))
                    elif typ=='submit':
                        ranked.append((2,999,e))
                except Exception:continue
            ranked.sort(key=lambda x:(x[0],x[1]))
            for _,__,e in ranked:
                try:
                    d.execute_script("arguments[0].scrollIntoView({block:'center'});",e)
                    d.execute_script('arguments[0].click();',e)
                    return True
                except Exception:
                    try:e.click();return True
                    except Exception:pass
            # 화면에 명시적인 버튼이 없으면 입력칸이 속한 폼을 제출한다.
            forms=d.find_elements(By.TAG_NAME,'form')
            for f in forms:
                try:
                    visible_inputs=[x for x in f.find_elements(By.CSS_SELECTOR,'input,select') if x.is_displayed()]
                    if not visible_inputs:continue
                    ok=d.execute_script("if(arguments[0].requestSubmit){arguments[0].requestSubmit();return true;} arguments[0].submit();return true;",f)
                    if ok:return True
                except Exception:continue
        except Exception:continue
    try:d.switch_to.default_content()
    except Exception:pass
    raise RuntimeError('조회/확인 버튼 또는 제출 가능한 폼을 찾지 못했습니다.')

def dump_debug(d,debug:Path,prefix):
    debug.mkdir(parents=True,exist_ok=True)
    try:d.save_screenshot(str(debug/f'{prefix}.png'))
    except:pass
    try:(debug/f'{prefix}.html').write_text(d.page_source,encoding='utf-8')
    except:pass

def parse_page(d):
    body=d.find_element(By.TAG_NAME,'body').text
    rows=[]
    for tr in d.find_elements(By.CSS_SELECTOR,'table tr'):
        cells=[re.sub(r'\s+',' ',c.text).strip() for c in tr.find_elements(By.CSS_SELECTOR,'th,td')]
        if cells:rows.append(cells)
    return body,rows

def choose_date_method(detail,rows):
    alltxt='\n'.join([' | '.join(r) for r in rows])+'\n'+detail
    ds=[]
    for m in re.finditer(r'(20\d{2})[.\-/년 ]+(\d{1,2})[.\-/월 ]+(\d{1,2})',alltxt):
        try:ds.append(date(int(m.group(1)),int(m.group(2)),int(m.group(3))).isoformat())
        except:pass
    method='온라인' if re.search(r'온라인|ZOOM|줌|비대면|LMS|VOD',alltxt,re.I) else ('대면' if re.search(r'대면|집합|연수원|교육장',alltxt,re.I) else '')
    return (ds[-1] if ds else ''),method

def fill_identity_form(d,name,resident,phone,need_phone=False):
    ins=[e for e in vis_inputs(d) if (e.get_attribute('type') or 'text').lower() in {'text','tel','number','password','search'}]
    if not ins:raise RuntimeError('입력칸을 찾지 못했습니다.')
    used=set()
    def pick(words,fallback=None):
        candidates=[e for e in ins if e not in used]
        if not candidates:return None
        e=max(candidates,key=lambda x:score(x,words))
        if score(e,words)==0 and fallback is not None and fallback<len(candidates):e=candidates[fallback]
        used.add(e);return e
    ne=pick(['name','성명','이름'],0); fill(ne,name)
    resident=clean_digits(resident)
    # 주민번호가 2칸이면 앞/뒤 분리
    rem=[e for e in ins if e not in used]
    rrank=sorted(rem,key=lambda e:score(e,['resident','jumin','주민','birth','생년']),reverse=True)
    if len(resident)>=13:
        if len(rrank)>=2 and (score(rrank[0],['주민'])>0 or len(ins)>=3):
            fill(rrank[0],resident[:6]);used.add(rrank[0]);fill(rrank[1],resident[6:13]);used.add(rrank[1])
        elif rrank:fill(rrank[0],resident)
    elif len(resident)>=6 and rrank:fill(rrank[0],resident[:6]);used.add(rrank[0])
    if phone:
        rem=[e for e in ins if e not in used]
        ph=[e for e in rem if score(e,['phone','mobile','휴대','전화'])>0]
        if len(ph)>=3:
            fill(ph[0],phone[:3]);fill(ph[1],phone[3:7]);fill(ph[2],phone[7:11])
        elif ph:fill(ph[0],phone)
        elif need_phone and rem:fill(rem[-1],phone)
    # 서울 수료조회 페이지에는 별도의 필수 동의 체크박스가 없다.

def _switch_to_kytti_input_context(d, timeout=12):
    """경기 페이지 입력칸이 본문 또는 iframe에 늦게 나타나는 경우까지 찾는다."""
    end=time.time()+timeout
    while time.time()<end:
        try:d.switch_to.default_content()
        except Exception:pass
        contexts=[None]
        try:
            frames=d.find_elements(By.CSS_SELECTOR,'iframe,frame')
            frames.sort(key=lambda f: 0 if ((f.get_attribute('name') or f.get_attribute('id') or '').lower()=='main') else 1)
            contexts += frames
        except Exception:pass
        for frame in contexts:
            try:
                d.switch_to.default_content()
                if frame is not None:
                    d.switch_to.frame(frame)
                inputs=[e for e in vis_inputs(d) if (e.get_attribute('type') or 'text').lower() in {'text','tel','number','password'}]
                ph=' '.join((e.get_attribute('placeholder') or '') for e in inputs)
                at=' '.join(attrs(e) for e in inputs)
                if len(inputs)>=3 and (('앞자리' in ph and '뒷자리' in ph) or ('주민' in at and ('이름' in at or '실명' in ph))):
                    return inputs
            except Exception:
                continue
        time.sleep(.4)
    try:d.switch_to.default_content()
    except Exception:pass
    return []

def fill_kytti_form(d,name,resident,mode='조회'):
    """경기도 페이지의 표시 문구/placeholder를 기준으로 정확히 입력한다."""
    inputs=_switch_to_kytti_input_context(d,12)
    name_el=next((e for e in inputs if '실명' in (e.get_attribute('placeholder') or '') or '이름' in attrs(e)),None)
    front_el=next((e for e in inputs if '앞자리' in (e.get_attribute('placeholder') or '') or any(k in attrs(e) for k in ('jumin1','resident1','birth'))),None)
    back_el=next((e for e in inputs if '뒷자리' in (e.get_attribute('placeholder') or '') or any(k in attrs(e) for k in ('jumin2','resident2'))),None)
    if not (name_el and front_el and back_el):
        raise RuntimeError(f'경기 실명인증 입력칸을 찾지 못했습니다. 표시 입력칸 수={len(inputs)}')
    resident=clean_digits(resident)
    if len(resident)!=13: raise RuntimeError('경기 조회에는 주민등록번호 13자리가 필요합니다.')
    fill(name_el,name);fill(front_el,resident[:6]);fill(back_el,resident[6:])
    set_required_consents(d,'경기',mode,'agree_ch')

def wait_after_submit(d,old_url,seconds=12):
    try:
        WebDriverWait(d,seconds).until(lambda x: x.current_url!=old_url or len(x.find_elements(By.CSS_SELECTOR,'table tr'))>1 or any(w in x.find_element(By.TAG_NAME,'body').text for w in ['검색결과','조회결과','예약내역','수료']))
    except Exception: pass
    time.sleep(1)

def _switch_to_form_context(d, minimum_inputs=2, timeout=12):
    """본문/iframe을 순회해 예약조회 입력 폼이 있는 문맥으로 전환한다."""
    end=time.time()+timeout
    while time.time()<end:
        try:d.switch_to.default_content()
        except Exception:pass
        contexts=[None]
        try:contexts += d.find_elements(By.CSS_SELECTOR,'iframe,frame')
        except Exception:pass
        for frame in contexts:
            try:
                d.switch_to.default_content()
                if frame is not None:d.switch_to.frame(frame)
                inputs=[e for e in vis_inputs(d) if (e.get_attribute('type') or 'text').lower() in {'text','tel','number','password','search'}]
                if len(inputs)>=minimum_inputs:return inputs
            except Exception:continue
        time.sleep(.35)
    try:d.switch_to.default_content()
    except Exception:pass
    return []

def fill_seoul_receipt_form(d,p:Person):
    """서울 수료증 발급/예약내역 통합 페이지의 본인확인 폼을 입력한다."""
    inputs=_switch_to_form_context(d,2,12)
    if not inputs:raise RuntimeError('서울 수료증 발급 조회 입력칸을 찾지 못했습니다.')
    resident=clean_digits(p.resident)
    if len(resident)<6:raise RuntimeError('서울 조회에는 생년월일 또는 주민번호 앞자리 6자가 필요합니다.')
    # 사이트 개편에 대비해 속성 점수와 화면 순서를 함께 사용한다.
    name_el=max(inputs,key=lambda e:score(e,['name','성명','이름']))
    fill(name_el,p.name)
    rem=[e for e in inputs if e!=name_el]
    rr=sorted(rem,key=lambda e:score(e,['jumin','resident','주민','birth','생년']),reverse=True)
    if len(resident)>=13 and len(rr)>=2:
        fill(rr[0],resident[:6]);fill(rr[1],resident[6:13])
    elif rr:
        fill(rr[0],resident[:6])
    set_required_consents(d,'서울','예약조회','cert1','cert2')

def fill_incheon_reservation_form(d,p:Person):
    """인천 집합교육 예약확인: 성명, 생년월일, 전화번호(010 선택)를 입력한다."""
    inputs=_switch_to_form_context(d,4,12)
    if not inputs:raise RuntimeError('인천 예약확인 입력칸을 찾지 못했습니다.')
    birth=clean_digits(p.resident)[:6]
    phone=clean_digits(p.phone)
    if len(birth)!=6:raise RuntimeError('인천 예약조회에는 생년월일 6자가 필요합니다.')
    if len(phone)!=11 or not phone.startswith('010'):
        raise RuntimeError('인천 예약조회에는 010으로 시작하는 휴대전화번호 11자리가 필요합니다.')
    # 현재 인천 폼의 정확한 필드 계약: phone1(select), phone2, phone3.
    phone1_candidates=d.find_elements(By.CSS_SELECTOR,"select[name='phone1']")
    phone1=next((e for e in phone1_candidates if e.is_displayed() and e.is_enabled()),None)
    if phone1 is None:
        raise RuntimeError('인천 휴대전화 앞자리 선택항목에서 010을 찾지 못했습니다.')
    try:
        selector=Select(phone1)
        selector.select_by_value('010')
        selected_value=(selector.first_selected_option.get_attribute('value') or '').strip()
        selected_text=(selector.first_selected_option.text or '').strip()
        if selected_value!='010' and selected_text!='010':
            raise RuntimeError('010 선택 상태를 확인하지 못했습니다.')
    except Exception as exc:
        raise RuntimeError(f'인천 휴대전화 앞자리 010 선택에 실패했습니다: {exc}') from exc
    name_el=input_by_name(d,'name') or max(inputs,key=lambda e:score(e,['name','성명','이름']))
    fill(name_el,p.name)
    rem=[e for e in inputs if e!=name_el]
    birth_el=input_by_name(d,'jumin1') or max(rem,key=lambda e:score(e,['birth','생년','주민','jumin']))
    fill(birth_el,birth)
    rem=[e for e in rem if e!=birth_el]
    phone_inputs=[e for e in (input_by_name(d,'phone2'),input_by_name(d,'phone3')) if e is not None]
    if len(phone_inputs)<2:
        phone_inputs=sorted(rem,key=lambda e:score(e,['phone','tel','휴대','연락']),reverse=True)
    tail=phone[3:]
    if len(phone_inputs)>=2:
        fill(phone_inputs[0],tail[:4]);fill(phone_inputs[1],tail[4:8])
    elif phone_inputs:
        fill(phone_inputs[0],tail)
    else:
        raise RuntimeError('인천 전화번호 뒤 8자리 입력칸을 찾지 못했습니다.')
    if ((phone_inputs[0].get_attribute('value') or '') != tail[:4] or
            (phone_inputs[1].get_attribute('value') or '') != tail[4:8]):
        raise RuntimeError('인천 휴대전화 뒤 8자리 입력값 검증에 실패했습니다.')
    print('FORM_INPUT|인천|예약조회|phone1=010|phone2=4자리|phone3=4자리|완료',flush=True)
    print('CONSENT|인천|예약조회|동의절차없음|완료',flush=True)

def _current_year_reservation(body,rows,region):
    """결과표에서 당해연도 예약/접수/교육예정 행만 추출한다."""
    year=date.today().year
    date_re=re.compile(r'(20\d{2})[.\-/년 ]+(\d{1,2})[.\-/월 ]+(\d{1,2})')
    candidates=[]
    row_texts=[' | '.join(text(x) for x in r) for r in rows]
    source=row_texts or [x.strip() for x in body.splitlines() if x.strip()]
    for line in source:
        compact=re.sub(r'\s+',' ',line).strip()
        # 수료증 발급만 있는 행은 예약으로 오인하지 않는다.
        reservation_signal=bool(re.search(r'예약|접수|신청|교육일|교육일자|수강일|입교|예정',compact))
        completion_only=bool(re.search(r'수료증|수료완료|이수완료|발급',compact)) and not bool(re.search(r'예약|접수|신청|예정',compact))
        if not reservation_signal or completion_only:continue
        for m in date_re.finditer(compact):
            try:
                iso=date(int(m.group(1)),int(m.group(2)),int(m.group(3))).isoformat()
            except Exception:continue
            if int(m.group(1))==year:candidates.append((iso,compact))
    if not candidates:return '', '', '', ''
    today=date.today()
    unique={iso:line for iso,line in candidates}
    future=sorted(x for x in unique if date_obj(x) and date_obj(x)>today)
    chosen=future[0] if future else max(unique)
    line=unique[chosen]
    method='온라인' if re.search(r'온라인|ZOOM|줌|비대면|LMS|VOD',line,re.I) else ('대면' if re.search(r'대면|집합|연수원|교육장',line,re.I) else '')
    return chosen,method,line,line

def reservation_lookup(d,region,p:Person,debug:Path,n:int)->ReservationResult:
    key=f'{region}예약'
    if key not in URLS:raise RuntimeError(f'{region} 예약조회 URL이 설정되지 않았습니다.')
    try:
        d.get(URLS[key])
    except TimeoutException:
        # edu.tredu.kr은 부가 리소스가 계속 로딩되어 d.get이 시간초과가 나도
        # main 프레임과 메뉴는 이미 표시되는 경우가 많다. 여기서 조회를 중단하지 않는다.
        try:d.execute_script('window.stop();')
        except Exception:pass
        print(f'NAVIGATION_TIMEOUT_RECOVERED|{region}|{URLS[key]}',flush=True)
    if region!='서울':
        WebDriverWait(d,25).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
    else:
        WebDriverWait(d,25).until(lambda x: len(x.find_elements(By.CSS_SELECTOR,"iframe[name='main'],frame[name='main'],iframe#main,frame#main"))>0 or len(x.find_elements(By.TAG_NAME,'body'))>0)
    if region=='서울':
        # 서울 예약조회는 차량번호를 입력하지 않는다.
        # 첫 화면이 카드형 메뉴이면 '교육 예약확인 및 변경' 화면으로 이동한다.
        if not _identity_input_ready(d):
            click_seoul_reservation_change(d,debug,f'{n:04d}_서울예약')
        fill_seoul_receipt_form(d,p)
    elif region=='경기':
        fill_kytti_form(d,p.name,p.resident,'예약조회')
    elif region=='인천':
        fill_incheon_reservation_form(d,p)
    else:
        raise RuntimeError(f'지원하지 않는 예약조회 지역입니다: {region}')
    old=d.current_url
    submit(d)
    if region=='서울':
        # 실명인증 후 표시되는 DIV/레이어 안내창을 닫고 예약목록을 읽는다.
        close_seoul_consent_popup(d,6)
    wait_after_submit(d,old,15)
    body,rows=parse_page(d);low=re.sub(r'\s+','',body)
    no_result_words=['조회된예약내역이없','예약내역이없','검색결과가없','조회결과가없','접수내역이없','해당자료가없','등록된자료가없']
    if any(x in low for x in no_result_words):
        return ReservationResult(False,region,status='예약없음',detail=body[:3000])
    rd,method,course,place=_current_year_reservation(body,rows,region)
    detail=('\n'.join(' | '.join(r) for r in rows) or body)[:3000]
    if not rd:
        return ReservationResult(False,region,status='예약없음',detail=detail)
    return ReservationResult(True,region,rd,method,'예약확인',course[:300],place[:300],detail)

def submit_seoul_completion(d):
    """서울 수료조회는 검색 버튼이 IMG + onclick 구조이므로 버튼 텍스트 탐색을 사용하지 않는다."""
    try:
        ok=d.execute_script("""
            var f=document.forms['af'] || document.getElementById('af');
            if(!f) return false;
            if(f.elements['flag']) f.elements['flag'].value='jumin';
            if(typeof window.on_search_NEW === 'function') { window.on_search_NEW('jumin'); return true; }
            f.submit(); return true;
        """)
        if ok is False:
            raise RuntimeError('서울 수료조회 폼(af)을 찾지 못했습니다.')
        return
    except Exception as e:
        raise RuntimeError(f'서울 수료조회 폼 제출 실패: {type(e).__name__}: {e}') from e

def _latest_completion_record(region, rows, body):
    """조회 결과에서 가장 최근 교육일과 그 행의 교육장/시간 정보를 찾는다."""
    candidates=[]
    for r in rows:
        joined=' | '.join(text(x) for x in r)
        m=re.search(r'(20\d{2})[.\-/년 ]+(\d{1,2})[.\-/월 ]+(\d{1,2})', joined)
        if not m:
            continue
        try:
            iso=date(int(m.group(1)),int(m.group(2)),int(m.group(3))).isoformat()
        except Exception:
            continue
        suffix=''
        place=''
        if region=='경기':
            # 경기 표의 마지막 열은 교육장이다. 동영상(VOD), 연수원 대강당 등을 원문대로 보존한다.
            values=[text(x).strip() for x in r if text(x).strip()]
            if values:
                place=values[-1]
                if re.fullmatch(r'20\d{2}-\d{1,2}-\d{1,2}', place):
                    place=''
            suffix=' '.join(x for x in ('경기',place) if x)
        elif region=='서울':
            # 서울 수료조회에는 온라인/대면 및 교육장 정보가 없으므로 '서울'로 통일한다.
            suffix='서울'
        else:
            # 인천은 현재 조회표에 장소가 명확히 표시되는 경우에만 원문을 보존한다.
            values=[text(x).strip() for x in r if text(x).strip()]
            possible=[v for v in values if re.search(r'교육장|연수원|강당|온라인|동영상|VOD|ZOOM|줌',v,re.I)]
            place=possible[-1] if possible else ''
            suffix=' '.join(x for x in ('인천',place) if x)
        candidates.append((iso,suffix,place,joined))
    if candidates:
        return max(candidates,key=lambda x:x[0])
    # 표 파싱이 안 된 경우 본문에서 날짜만이라도 보존한다.
    dates=[]
    for m in re.finditer(r'(20\d{2})[.\-/년 ]+(\d{1,2})[.\-/월 ]+(\d{1,2})', body):
        try: dates.append(date(int(m.group(1)),int(m.group(2)),int(m.group(3))).isoformat())
        except Exception: pass
    if dates:
        iso=max(dates)
        return iso,region,'',body[:500]
    return '','','',''

def _completion_year(value):
    d=normalize_date(value)
    try:return int(d[:4]) if d else None
    except Exception:return None

def merge_multi_completion(results):
    """서울·경기·인천 결과 중 당해연도 수료가 하나라도 있으면 수료로 확정한다."""
    current_year=date.today().year
    completed=[(r,c) for r,c in results if c.status=='교육수료' and _completion_year(c.completion_date)==current_year]
    if completed:
        completed.sort(key=lambda rc: normalize_date(rc[1].completion_date) or '', reverse=True)
        region,comp=completed[0]
        detail='\n\n'.join(f'[{r}]\n{c.detail or c.error}' for r,c in results)
        comp.detail=detail[:5000]
        return region,comp
    # 당해연도 수료가 없으면 양쪽의 가장 최근 과거 수료일은 표시용으로 보존한다.
    dated=[(r,c) for r,c in results if normalize_date(c.completion_date)]
    if dated:
        dated.sort(key=lambda rc: normalize_date(rc[1].completion_date) or '', reverse=True)
        region,old=dated[0]
        detail='\n\n'.join(f'[{r}]\n{c.detail or c.error}' for r,c in results)
        return region,CompletionResult('미수료',old.completion_date,'미수료',old.course,old.place,detail[:5000])
    details='\n\n'.join(f'[{r}]\n{c.detail or c.error}' for r,c in results)
    if results and all(c.category=='입력정보부족' for _,c in results):
        return '+'.join(r for r,_ in results) or '전체기관',CompletionResult('미수료','입력정보부족','입력정보부족',detail=details[:5000])
    if any(c.category=='조회오류' for _,c in results):
        return '+'.join(r for r,_ in results) or '전체기관',CompletionResult('미수료','조회오류','조회오류',detail=details[:5000])
    return '+'.join(r for r,_ in results) or '전체기관',CompletionResult('미수료','결과없음','결과없음',detail=details[:5000])

def fill_incheon_form(d,name,birth):
    """인천교통연수원 개인 이수확인: 이름, 생년월일, 개인정보 동의 후 조회."""
    birth=clean_digits(birth)[:6]
    if len(birth)!=6:
        raise RuntimeError('인천 조회에는 생년월일 6자리가 필요합니다.')
    end=time.time()+12
    while time.time()<end:
        try:d.switch_to.default_content()
        except Exception:pass
        contexts=[None]
        try:contexts += d.find_elements(By.CSS_SELECTOR,'iframe,frame')
        except Exception:pass
        for frame in contexts:
            try:
                d.switch_to.default_content()
                if frame is not None:d.switch_to.frame(frame)
                ins=[e for e in vis_inputs(d) if (e.get_attribute('type') or 'text').lower() in {'text','tel','number'}]
                # The page also contains a visible global search input named
                # "keyword", so never use input order as an identity fallback.
                name_el=input_by_name(d,'completion_name')
                birth_el=input_by_name(d,'resident_registration')
                if not name_el:
                    name_el=next((e for e in ins if any(k in attrs(e) for k in ('name','성명','이름')) and 'keyword' not in attrs(e)),None)
                if not birth_el:
                    birth_el=next((e for e in ins if any(k in attrs(e) for k in ('birth','생년','birthday','resident_registration','jumin')) and e is not name_el),None)
                if name_el and birth_el:
                    fill(name_el,name);fill(birth_el,birth)
                    set_required_consents(d,'인천','수료조회','policy')
                    return
            except Exception:continue
        time.sleep(.4)
    raise RuntimeError('인천 이름·생년월일 입력칸을 찾지 못했습니다.')

def submit_incheon_completion(d):
    """인천 개인 이수확인 조회 버튼을 명시적으로 누른다.

    공용 submit()은 '내용보기' 같은 보조 버튼을 먼저 선택할 수 있으므로,
    인천 수료조회에서는 조회 버튼과 폼만 제한적으로 사용한다.
    """
    try:
        d.switch_to.default_content()
    except Exception:
        pass
    contexts=[None]
    try:
        contexts += [f for f in d.find_elements(By.CSS_SELECTOR,'iframe,frame') if f.is_displayed()]
    except Exception:
        pass
    for frame in contexts:
        try:
            d.switch_to.default_content()
            if frame is not None:
                d.switch_to.frame(frame)
            candidates=d.find_elements(By.CSS_SELECTOR,"button,input[type='submit'],input[type='button'],a,[role='button'],[onclick]")
            ranked=[]
            for e in candidates:
                try:
                    if not e.is_displayed() or not e.is_enabled():
                        continue
                    raw=' '.join(filter(None,[(e.text or '').strip(),(e.get_attribute('value') or '').strip(),(e.get_attribute('title') or '').strip(),(e.get_attribute('aria-label') or '').strip(),(e.get_attribute('alt') or '').strip()]))
                    compact=re.sub(r'\s+','',raw)
                    # '내용보기', 개인정보 보기/약관 버튼은 절대 조회 버튼으로 선택하지 않는다.
                    if any(x in compact for x in ('내용보기','약관','개인정보처리방침')):
                        continue
                    if compact in ('조회','조회하기','검색','확인'):
                        ranked.append((0,len(compact),e))
                    elif '조회' in compact:
                        ranked.append((1,len(compact),e))
                except Exception:
                    continue
            ranked.sort(key=lambda x:(x[0],x[1]))
            for _,__,e in ranked:
                try:
                    d.execute_script("arguments[0].scrollIntoView({block:'center'});",e)
                    d.execute_script('arguments[0].click();',e)
                    return True
                except Exception:
                    try:
                        e.click(); return True
                    except Exception:
                        pass
            # 조회 버튼을 못 찾은 경우 이름/생년월일 입력칸이 속한 폼만 제출한다.
            for f in d.find_elements(By.TAG_NAME,'form'):
                try:
                    body=(f.text or '')
                    if not ('이름' in body and '생년월일' in body):
                        continue
                    ok=d.execute_script("if(arguments[0].requestSubmit){arguments[0].requestSubmit();return true;} arguments[0].submit();return true;",f)
                    if ok:
                        return True
                except Exception:
                    pass
        except Exception:
            continue
    try:
        d.switch_to.default_content()
    except Exception:
        pass
    raise RuntimeError('인천 수료조회 버튼을 찾지 못했습니다.')

def completion_lookup(d,region,p:Person,debug:Path,n:int)->CompletionResult:
    try:d.switch_to.default_content()
    except Exception:pass
    url=URLS[f'{region}수료']
    if region in ('경기','인천'):
        sep='&' if '?' in url else '?'
        url=f'{url}{sep}_zc={int(time.time()*1000)}'
    d.get(url);WebDriverWait(d,20).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
    old=d.current_url
    if region=='서울':
        fill_identity_form(d,p.name,p.resident[:6],p.phone);submit_seoul_completion(d)
    elif region=='경기':
        if len(p.resident)!=13:return CompletionResult('미수료','입력정보부족','입력정보부족',detail='경기 수료조회는 주민번호 13자리가 필요합니다.')
        inputs=_switch_to_kytti_input_context(d,10)
        if not inputs:
            try:d.switch_to.default_content()
            except Exception:pass
            d.refresh();WebDriverWait(d,20).until(EC.presence_of_element_located((By.TAG_NAME,'body')))
        fill_kytti_form(d,p.name,p.resident,'수료조회');submit(d)
    else:
        fill_incheon_form(d,p.name,p.resident[:6]);submit_incheon_completion(d)
    wait_after_submit(d,old);body,rows=parse_page(d); compact=re.sub(r'\s+','',body)
    if any(x in compact for x in ['검색결과가없','조회된결과가없','수료내역이없']):
        return CompletionResult('미수료','결과없음','결과없음',detail=body[:1500])
    alltxt='\n'.join(' | '.join(r) for r in rows)+'\n'+body
    iso,suffix,latest_place,latest_row=_latest_completion_record(region,rows,body)
    cdate=' '.join(x for x in (iso,suffix) if x).strip()
    has_completion=bool(re.search(r'수료|이수완료|교육완료',alltxt)) and not bool(re.search(r'미수료|미이수',latest_row or ''))
    current_year=date.today().year
    # 인천 개인 이수확인 결과표에 교육기록이 표시되면 그 행 자체가 이수내역이다.
    # 페이지 공통 안내문에 '미수료' 문구가 섞여 있어도 결과 행의 당해연도 날짜를 우선한다.
    if region=='인천':
        completed=bool(iso) and int(iso[:4])==current_year and not bool(re.search(r'수료내역이없|조회된결과가없|검색결과가없',re.sub(r'\s+','',latest_row or '')))
    else:
        completed=has_completion and bool(iso) and int(iso[:4])==current_year
    status='교육수료' if completed else '미수료'
    cat='교육수료' if completed else ('미수료' if iso else '결과없음')
    if not iso and cat=='결과없음':
        cdate='결과없음'
    course='';place=latest_place
    # 가장 최근 행을 우선하여 과정 정보를 저장한다.
    if latest_row and re.search(r'보수|신규|강화|법령|교육',latest_row):
        course=latest_row
    else:
        for r in rows:
            j=' | '.join(r)
            if re.search(r'보수|신규|강화|법령|교육',j):course=j
    return CompletionResult(status,cdate,cat,course[:300],place[:300],alltxt[:3000])

def reservation_date_from_completion_detail(detail):
    """수료조회 결과 화면에 예약/예정/교육일이 함께 표시될 때만 보수적으로 날짜를 추출한다.
    일반 과거 수료일은 예약일로 오인하지 않는다.
    """
    raw=text(detail)
    if not raw:
        return ''
    candidates=[]
    pattern=re.compile(r'(20\d{2})[.\-/년 ]+(\d{1,2})[.\-/월 ]+(\d{1,2})')
    for line in raw.splitlines():
        compact=re.sub(r'\s+',' ',line).strip()
        if not re.search(r'예약|예정|교육일|교육일자|수강일|시청일|입교',compact):
            continue
        for m in pattern.finditer(compact):
            try:
                iso=date(int(m.group(1)),int(m.group(2)),int(m.group(3))).isoformat()
                candidates.append(iso)
            except Exception:
                pass
    if not candidates:
        return ''
    # 교육시청일 자동 변경은 오늘 이후의 실제 예정일에만 허용한다.
    # 과거 교육일/수료일(예: 7/27 미수료)은 기존 교육시청일을 덮어쓰면 안 된다.
    today=date.today()
    future=sorted(x for x in set(candidates) if date_obj(x) and date_obj(x)>today)
    return future[0] if future else ''

def save_db(db:Path,p:Person,res:ReservationResult,comp:CompletionResult):
    with sqlite3.connect(db) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS education_history(id INTEGER PRIMARY KEY AUTOINCREMENT,checked_at TEXT,company TEXT,name TEXT,resident_hash TEXT,phone_tail TEXT,site TEXT,reservation_date TEXT,method TEXT,reservation_status TEXT,completion_status TEXT,completion_date TEXT,category TEXT,course TEXT,place TEXT,detail TEXT)''')
        import hashlib
        h=hashlib.sha256(p.resident.encode()).hexdigest()[:20] if p.resident else ''
        con.execute('INSERT INTO education_history(checked_at,company,name,resident_hash,phone_tail,site,reservation_date,method,reservation_status,completion_status,completion_date,category,course,place,detail) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(datetime.now().isoformat(timespec='seconds'),p.company,p.name,h,p.phone[-4:],res.site,res.reservation_date,res.method,res.status,comp.status,comp.completion_date,comp.category,comp.course or res.course,comp.place or res.place,(res.detail+'\n'+comp.detail)[:5000]))
        con.commit()

def visible_result_values(row):
    """사용자가 보는 기존 양식(M:수료여부, N:수료일)에 맞춘 표시값."""
    reason=exclusion_reason(row)
    if reason:
        return '제외', f'조회제외({reason})'
    final_date,_face_note=_split_final_completion_and_face_schedule(row.get('수료일',''))
    if hold_reason(row):
        return '미수료', final_date or text(row.get('수료일','')) or '결과없음'
    status=canonical_completion_status(row.get('수료여부',''))
    category=text(row.get('구분','')).replace(' ','')
    completion=text(row.get('수료일',''))
    if status=='교육수료' and _completion_year(completion)==date.today().year:
        return '수료', completion
    if status=='교육수료':
        # 과거연도 수료기록은 날짜를 보존하되 당해연도 기준으로는 미수료다.
        return '미수료', completion or '결과없음'
    if category=='조회오류':
        return '미수료', '조회오류'
    if category=='입력정보부족':
        return '미수료', '입력정보부족'
    if category=='결과없음' and not completion:
        return '미수료', '결과없음'
    return '미수료', completion or ('결과없음' if category=='결과없음' else '')

def write_result(input_path:Path,sheet_name:str,header_row:int,df:pd.DataFrame,out:Path):
    status_colors={
        '수료':('C6EFCE','006100'),
        '미수료':('FFC7CE','9C0006'),
        '제외':('E7E6E6','595959'),
    }
    def excel_rgb(hex_color):
        value=hex_color.lstrip('#')
        r,g,b=(int(value[i:i+2],16) for i in (0,2,4))
        return r+(g<<8)+(b<<16)
    # Windows Excel COM 우선: 서식과 .xls 호환 보존
    try:
        import win32com.client
        app=win32com.client.DispatchEx('Excel.Application');app.Visible=False;app.DisplayAlerts=False
        wb=app.Workbooks.Open(str(input_path));ws=wb.Worksheets(sheet_name)
        used=ws.UsedRange;last_col=used.Column+used.Columns.Count-1
        headers={str(ws.Cells(header_row+1,c).Value).strip():c for c in range(1,last_col+1) if ws.Cells(header_row+1,c).Value is not None}
        for col in OUT_COLS:
            if col not in headers:last_col+=1;headers[col]=last_col;ws.Cells(header_row+1,last_col).Value=col
        for idx,row in df.iterrows():
            excel_row=header_row+2+idx
            visible_status,visible_date=visible_result_values(row)
            for c in OUT_COLS:
                value=text(row.get(c,''))
                if c=='수료여부': value=visible_status
                elif c=='수료일': value=visible_date
                ws.Cells(excel_row,headers[c]).Value=value
            if headers.get('수료여부') and visible_status in status_colors:
                fill_color,font_color=status_colors[visible_status]
                status_cell=ws.Cells(excel_row,headers['수료여부'])
                status_cell.Interior.Color=excel_rgb(fill_color)
                status_cell.Font.Color=excel_rgb(font_color)
            # 예약 변경으로 갱신된 교육시청일과 비고 사유는 기존 원본 열에 다시 기록한다.
            for c in ('교육시청일','기수','비고'):
                if c in headers and c in df.columns:
                    ws.Cells(excel_row,headers[c]).Value=text(row.get(c,''))
        ws.Range(ws.Cells(header_row+1,min(headers.values())),ws.Cells(header_row+1,max(headers.values()))).Font.Bold=True
        # 기존 신청양식처럼 수료여부/수료일만 보이고 내부 관리열은 위치와 관계없이 모두 숨긴다.
        visible_names={'수료여부','수료일'}
        for c in OUT_COLS:
            if c not in visible_names and headers.get(c):
                ws.Columns(headers[c]).Hidden=True
        # 결과 파일의 열 간격이 과도하게 넓어지지 않도록 신청양식 기준으로 폭을 고정한다.
        compact_widths={
            '소속(회사명)':18,'소속':18,'회사명':18,'이름':10,
            '주민번호 앞자리':12,'주민번호 뒷자리':14,
            '휴대폰번호1':8,'휴대폰번호2':9,'휴대폰번호3':9,
            '업종':9,'조합/협회':12,'교육시청일':12,'기수':8,
            '수료여부':10,'수료일':25,
        }
        for name,w in compact_widths.items():
            if headers.get(name):
                ws.Columns(headers[name]).ColumnWidth=w
        try:
            ws.UsedRange.Rows.RowHeight=20
        except Exception:
            pass
        wb.SaveAs(str(out),FileFormat=51);wb.Close(False);app.Quit();clean_saved_xlsx(out);return
    except Exception as e:
        print('EXCEL_COM_FALLBACK|'+str(e),flush=True)
    # fallback xlsx
    from openpyxl import load_workbook
    from openpyxl.styles import PatternFill
    from copy import copy
    src=sanitize_xlsx(input_path)
    if input_path.suffix.lower()=='.xls':
        raise RuntimeError('Excel COM을 사용할 수 없어 .xls 저장이 불가능합니다. Microsoft Excel이 설치된 Windows에서 실행하세요.')
    wb=load_workbook(src);ws=wb[sheet_name]
    headers={text(ws.cell(header_row+1,c).value):c for c in range(1,ws.max_column+1)};last=ws.max_column
    for col in OUT_COLS:
        if col not in headers:last+=1;headers[col]=last;ws.cell(header_row+1,last,col)
    for idx,row in df.iterrows():
        er=header_row+2+idx
        visible_status,visible_date=visible_result_values(row)
        for c in OUT_COLS:
            value=text(row.get(c,''))
            if c=='수료여부': value=visible_status
            elif c=='수료일': value=visible_date
            ws.cell(er,headers[c],value)
        if headers.get('수료여부') and visible_status in status_colors:
            fill_color,font_color=status_colors[visible_status]
            status_cell=ws.cell(er,headers['수료여부'])
            status_cell.fill=PatternFill(fill_type='solid',fgColor=fill_color)
            status_font=copy(status_cell.font)
            status_font.color=font_color
            status_cell.font=status_font
        for c in ('교육시청일','기수','비고'):
            if c in headers and c in df.columns:
                ws.cell(er,headers[c],text(row.get(c,'')))
    for c in OUT_COLS:
        if c not in {'수료여부','수료일'} and headers.get(c):
            ws.column_dimensions[ws.cell(1,headers[c]).column_letter].hidden=True
    compact_widths={
        '소속(회사명)':18,'소속':18,'회사명':18,'이름':10,
        '주민번호 앞자리':12,'주민번호 뒷자리':14,
        '휴대폰번호1':8,'휴대폰번호2':9,'휴대폰번호3':9,
        '업종':9,'조합/협회':12,'교육시청일':12,'기수':8,
        '수료여부':10,'수료일':25,
    }
    for name,w in compact_widths.items():
        if headers.get(name):
            ws.column_dimensions[ws.cell(1,headers[name]).column_letter].width=w
    for row_cells in ws.iter_rows(min_row=header_row+1,max_row=ws.max_row):
        ws.row_dimensions[row_cells[0].row].height=20
    wb.save(out)
    clean_saved_xlsx(out)



def _first_row_text(row, names):
    for name in names:
        if name in row.index:
            v=text(row.get(name,''))
            if v:
                return v
    return ''

def hold_reason(row):
    """비고에 적힌 보류 사유. 보류는 미수료로 집계하지만 자동 조회에서는 제외한다."""
    note=_first_row_text(row,['비고','메모','특이사항','퇴사여부','재직여부'])
    compact=text(note).replace(' ','')
    return note if compact and '보류' in compact else ''

def exclusion_reason(row):
    """퇴사·명시적 제외 사유가 있는 행은 모든 조회/재조회에서 제외한다."""
    note=_first_row_text(row,['비고','메모','특이사항','퇴사여부','재직여부'])
    compact=text(note).replace(' ','')
    if not compact or '보류' in compact:
        return ''
    if any(k in compact for k in ('퇴사자','퇴사','조회제외','수료조회제외','대상제외')):
        return note
    if compact=='제외' or compact.startswith('제외-') or compact.startswith('제외:') or compact.endswith('제외'):
        return note
    return ''

def exclusion_kind(row):
    return '제외' if exclusion_reason(row) else ''

def _append_note(row, message):
    old=_first_row_text(row,['비고','메모','특이사항'])
    if not message:
        return old
    if message in old:
        return old
    return f'{old} / {message}'.strip(' /') if old else message

def _split_final_completion_and_face_schedule(value):
    """'최종수료 YYYY-MM-DD / YYYY-MM-DD 대면교육 예정'을 실제 수료일과 예정 메모로 분리한다."""
    raw=text(value)
    m=re.search(r'최종수료\s*(20\d{2}[-./]\d{1,2}[-./]\d{1,2}).*?(20\d{2}[-./]\d{1,2}[-./]\d{1,2})\s*대면교육',raw)
    if not m:
        return '', ''
    final_date=normalize_date(m.group(1)) or m.group(1)
    scheduled=normalize_date(m.group(2)) or m.group(2)
    return final_date, f'대면교육 입교예정일 {scheduled}'

def normalize_manual_result_rows(df):
    """기존 혼합 표기를 정리한다: 수료일에는 최종 수료일만, 대면교육 예정일은 비고로 이동."""
    if '비고' not in df.columns:
        df['비고']=''
    for idx,row in df.iterrows():
        final_date,face_note=_split_final_completion_and_face_schedule(row.get('수료일',''))
        if final_date:
            df.at[idx,'수료일']=final_date
            df.at[idx,'수료여부']='교육수료' if _completion_year(final_date)==date.today().year else '미수료'
            df.at[idx,'구분']='교육수료' if _completion_year(final_date)==date.today().year else '미수료'
            df.at[idx,'비고']=_append_note(row,face_note)
            # 대면교육 예정은 온라인 교육시청일/기수로 관리하지 않는다.
            if '교육시청일' in df.columns: df.at[idx,'교육시청일']=''
            if '기수' in df.columns: df.at[idx,'기수']=''
    return df

def _cohort_number(row):
    raw=_first_row_text(row,['기수','교육기수','차수'])
    m=re.search(r'\d+',raw)
    return int(m.group()) if m else None

def _is_online_training(row,res=None,site=''):
    parts=[_first_row_text(row,['교육방식','교육형태','방식']),_first_row_text(row,['교육장소','교육장','장소'])]
    if res is not None:
        parts += [text(getattr(res,'method','')),text(getattr(res,'place','')),text(getattr(res,'detail',''))]
    joined=' '.join(parts).lower()
    if any(k in joined for k in ('온라인','zoom','줌','vod','동영상','비대면')):
        return True
    # 서울 온라인 단체예약은 사용자가 기수를 유지하고, 대면/타지역 교육은 기수를 지우는 방식으로 관리한다.
    return site=='서울' and _cohort_number(row) in SEOUL_ONLINE_SCHEDULE_2026

def online_training_date(row,res=None,site=''):
    """예약조회 사이트에서 실제로 확인된 예약일만 교육시청일 후보로 반환한다."""
    if res is None or not bool(getattr(res,'found',False)):
        return ''
    return normalize_date(getattr(res,'reservation_date',''))

def requested_training_date(row,p=None):
    """예정일은 원본의 교육시청일을 최우선으로 사용한다."""
    raw=_first_row_text(row,['교육시청일','교육 시청일','예정일','예약일','교육일','시청일'])
    return normalize_date(raw) or (p.requested_date if p else '')


def reservation_date_from_region_detail(detail, region):
    """통합 수료조회 상세 중 지정 기관 구간에서만 예약/예정일을 찾는다.

    v14.4: 수료조회 과정에서 교육시청일을 자동 갱신하는 것은 경기 사이트에서
    실제 미래 예약일이 확인된 경우로 제한한다. 서울에서 예약일을 확인하지 못한
    경우에는 사용자가 입력한 기존 교육시청일을 그대로 보존한다.
    """
    raw=text(detail)
    if not raw:
        return ''
    marker=f'[{region}]'
    start=raw.find(marker)
    if start < 0:
        return ''
    end=len(raw)
    for other in ('서울','경기','인천'):
        if other==region:
            continue
        pos=raw.find(f'[{other}]', start+len(marker))
        if pos >= 0:
            end=min(end,pos)
    return reservation_date_from_completion_detail(raw[start:end])


def status_change_reason(before_key, after_key, old_date, new_date, discovered_region=''):
    if before_key==after_key and normalize_date(old_date)==normalize_date(new_date):
        return ''
    if after_key=='교육수료':
        return '당해연도 교육수료 확인'
    if after_key=='입교예정':
        return f'{discovered_region} 미래 예약일 조회'.strip() if discovered_region else '미래 교육시청일 확인'
    if before_key=='입교예정' and after_key=='미수료':
        return '예약일 경과 후 당해연도 수료 미확인'
    return '조회 결과에 따른 상태 재판정'


def write_change_log(out_path, changes):
    """조회로 상태 또는 교육시청일이 바뀐 대상만 별도 엑셀로 저장한다."""
    if not changes:
        return None
    log_dir=Path(out_path).parent/'logs'
    log_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    log_path=log_dir/f'{stamp}_상태변경로그.xlsx'
    pd.DataFrame(changes).to_excel(log_path,index=False)
    return log_path


def month_day_display(value):
    """수료일/예약일을 신청양식의 교육시청일 형식(M/D)으로 변환한다."""
    d=date_obj(normalize_date(value))
    return f'{d.month}/{d.day}' if d else ''

def completion_training_note(comp):
    """일반 줌교육 외 교육종류가 명확한 경우 비고에 남길 문구를 만든다."""
    joined=' '.join([text(getattr(comp,'course','')), text(getattr(comp,'category','')), text(getattr(comp,'detail',''))])
    if '법령위반' in joined:
        return '법령위반교육'
    return ''

def canonical_completion_status(value):
    raw=text(value).replace(' ','')
    if not raw:
        return ''
    completed={'교육수료','수료자','수료','이수완료','교육완료','완료','이수','수료완료','O','○','Y','YES','TRUE'}
    incomplete={'미수료','미이수','불참','미참석','X','×','N','NO','FALSE'}
    up=raw.upper()
    if raw in completed or up in completed:
        return '교육수료'
    if raw in incomplete or up in incomplete:
        return '미수료'
    if '미수료' in raw or '미이수' in raw:
        return '미수료'
    if any(k in raw for k in ('수료자','교육수료','이수완료','교육완료','수료완료')):
        return '교육수료'
    return ''

def row_result_state(row):
    """현황판의 기본 판정: 보류/제외 → 2026 수료 → 미래 입교예정 → 미수료."""
    reason=exclusion_reason(row)
    if reason:
        return '제외','제외',reason
    if hold_reason(row):
        return '미수료','미수료','보류'

    status_raw=_first_row_text(row, ['수료여부','수료 여부','수료결과','수료 결과','교육수료여부','이수여부','이수 여부','결과'])
    category_raw=_first_row_text(row, ['구분','상태','조회상태'])
    completion_raw=_first_row_text(row,['수료일','수료 일자','수료일자','교육일자'])
    category=text(category_raw).replace(' ','')

    # 최종 수료일이 올해(2026년)이면 지역/교육방식과 관계없이 수료.
    if _completion_year(completion_raw)==date.today().year:
        return '교육수료','교육수료',category_raw or '교육수료'

    # 올해 수료가 아니고 교육시청일이 현재 이후이면 입교예정.
    rdate=requested_training_date(row)
    rd=date_obj(rdate)
    if rd and rd>date.today():
        return '입교예정','미수료','입교예정'

    # 결과없음/조회오류 등은 세부 사유로 보존하되 기본 인원은 모두 미수료에 포함.
    if category in ('결과없음','조회오류','입력정보부족','예약확인필요','정보변경확인'):
        return '미수료','미수료',category

    return '미수료','미수료',category_raw or '미수료'

def _raw_result_fields(row):
    return {
        'status': _first_row_text(row,['수료여부','수료 여부','수료결과','수료 결과','교육수료여부','이수여부','이수 여부','결과']),
        'date': _first_row_text(row,['수료일','수료 일자','수료일자','교육일자']),
        'category': _first_row_text(row,['구분','상태','조회상태']),
        'detail': _first_row_text(row,['수료조회내용','조회내용','비고']),
        'checked': _first_row_text(row,['최종조회일시','조회일시','최종 조회일시']),
    }

def _normalize_status_filters(status_filter):
    """상태 필터를 중복 선택 가능한 집합으로 정규화한다."""
    if status_filter is None:
        return {'all'}
    if isinstance(status_filter, (list, tuple, set)):
        items=[text(x).strip() for x in status_filter]
    else:
        items=[x.strip() for x in text(status_filter).split(',')]
    items={x for x in items if x}
    return {'all'} if not items or 'all' in items else items


def row_matches_filters(row,p,date_filter='all',status_filter='all',today=None):
    """날짜 조건과 복수 상태 조건을 조합해 조회 대상을 선별한다."""
    today=today or date.today()
    key,status,cat=row_result_state(row)
    raw=_raw_result_fields(row)
    rdate=requested_training_date(row,p)
    rd=date_obj(rdate)
    combined=' '.join(text(x) for x in (raw['status'],raw['date'],raw['category'],raw['detail'])).replace(' ','')

    # 오늘까지: 예약일이 오늘 이하인 경우만 포함한다. 예약일 공란은 제외한다.
    if date_filter=='due' and not (rd and rd<=today):
        return False

    # 제외 여부는 현재 인사/제외 사유와 최종 현황 판정만 사용한다.
    # 과거 조회에서 남은 '구분=제외' 문구만으로 현재 미수료자를 누락시키지 않는다.
    ex=bool(exclusion_reason(row)) or key=='제외'
    hold=bool(hold_reason(row)) or cat=='보류'
    is_error=(cat in ('조회오류','결과없음','입력정보부족') or
              any(x in combined for x in ('조회오류','결과없음','입력정보부족','검색결과가없')) or
              'ERROR' in combined.upper())
    is_completed=(status=='교육수료' or key=='교육수료')
    is_scheduled=(cat=='입교예정' or (not is_completed and bool(rd and rd>today)))
    is_incomplete=(status=='미수료' and cat not in ('입교예정','보류') and not ex)

    filters=_normalize_status_filters(status_filter)
    if 'all' in filters:
        return True

    matches={
        'completed': is_completed,
        'incomplete': is_incomplete,
        'scheduled': is_scheduled,
        'hold': hold,
        'excluded': ex,
        'error': is_error,
    }
    return any(matches.get(f,False) for f in filters)

def row_matches_target(row,p,target,today=None):
    """이전 버튼/명령행과 호환되는 대상 선별."""
    today=today or date.today()
    key,status,cat=row_result_state(row)
    raw=_raw_result_fields(row)
    cdate=text(raw['date']).strip()
    rdate=requested_training_date(row,p)
    rd=date_obj(rdate)
    combined=' '.join(text(x) for x in (raw['status'],raw['date'],raw['category'],raw['detail'])).replace(' ','')

    if target=='all': return row_matches_filters(row,p,'all','all',today)
    if target=='due': return row_matches_filters(row,p,'due','all',today)
    if target=='completed': return row_matches_filters(row,p,'all','completed',today)
    if target=='incomplete': return row_matches_filters(row,p,'all','incomplete',today)
    if target=='incomplete_all': return status=='미수료'
    if target=='scheduled_completion': return row_matches_filters(row,p,'all','scheduled',today)
    if target=='hold': return row_matches_filters(row,p,'all','hold',today)
    if target=='excluded': return row_matches_filters(row,p,'all','excluded',today)
    if target=='error_all': return row_matches_filters(row,p,'all','error',today)
    if target=='unqueried':
        return not any(text(raw[k]).strip() for k in ('status','date','category','detail','checked'))
    if target=='completion_blank': return not cdate
    if target=='reservation_blank': return not normalize_date(rdate)
    if target=='noresult': return cat=='결과없음' or '결과없음' in combined or '검색결과가없' in combined
    if target=='error': return cat=='조회오류' or '조회오류' in combined or 'ERROR' in combined.upper()
    if target=='input_missing': return cat=='입력정보부족' or '입력정보부족' in combined
    if target=='changed_reservation':
        fp=row_fingerprint(row); keyp=person_key(p.name,p.resident,p.phone); st=get_state(keyp)
        if status=='교육수료': return False
        if not normalize_date(rdate): return True
        if not st or not str(st[0] or '').startswith('v2:'): return False
        return fp != (st[0] or '')
    return True

def count_target_rows(df,target):
    people=people_from_df(df)
    return sum(1 for p in people if row_matches_target(df.loc[p.row],p,target))

def count_filter_rows(df,date_filter='all',status_filter='all'):
    people=people_from_df(df)
    return sum(1 for p in people if row_matches_filters(df.loc[p.row],p,date_filter,status_filter))

def summary_counts(df,people):
    keys=['전체','교육수료','입교예정','미수료','보류','제외','예약확인필요','정보변경확인','결과없음','조회오류','입력정보부족','미조회']
    counts={k:0 for k in keys}; counts['전체']=len(people)
    for p in people:
        key,_,cat=row_result_state(df.loc[p.row])
        counts[key]=counts.get(key,0)+1
        # 세부 오류/확인 상태는 미수료 총계와 별도로 중복 표시한다.
        if key=='미수료' and cat in ('보류','예약확인필요','정보변경확인','결과없음','조회오류','입력정보부족'):
            counts[cat]=counts.get(cat,0)+1
    return counts

def main():
    ap=argparse.ArgumentParser();ap.add_argument('input');ap.add_argument('--output');ap.add_argument('--regions',default='서울,경기,인천');ap.add_argument('--headless',action='store_true');ap.add_argument('--browser-mode',choices=['hidden','background','normal'],default='hidden');ap.add_argument('--limit',type=int,default=0);ap.add_argument('--resume-row',type=int,default=-1);ap.add_argument('--mode',choices=['all','reservation','completion'],default='all');ap.add_argument('--target',choices=['all','unqueried','due','incomplete','incomplete_all','completion_blank','reservation_blank','noresult','error','input_missing','changed_reservation','scheduled_completion','completed','hold','excluded','error_all'],default='all');ap.add_argument('--control-file',default='');ap.add_argument('--date-filter',choices=['all','due'],default='all');ap.add_argument('--status-filter',default='all',help='쉼표로 구분한 복수 상태: completed,incomplete,scheduled,hold,excluded,error 또는 all');args=ap.parse_args()
    global BROWSER_MODE
    BROWSER_MODE=args.browser_mode
    # v13: 기본 조회는 수료 중심이다. 예약조회는 UI의 별도 버튼에서만 reservation 모드로 실행한다.
    # 과거 실행 인자 all은 안전을 위해 completion으로 해석하여 두 기능이 한 번에 섞이지 않게 한다.
    if args.mode == 'all':
        print('INFO|통합모드는 안전을 위해 수료조회로 전환: all -> completion', flush=True)
        args.mode = 'completion'
    print(f'QUERY_MODE|{args.mode}', flush=True)
    if args.mode == 'reservation':
        print('MODE_GUARD|예약조회 전용|수료조회 URL 차단', flush=True)
    elif args.mode == 'completion':
        print('MODE_GUARD|수료조회 전용|예약조회 로직 차단', flush=True)
    control=Path(args.control_file) if args.control_file else None
    def stop_requested():
        try:
            return bool(control and control.exists() and control.read_text(encoding='utf-8',errors='ignore').strip().upper()=='STOP')
        except Exception:
            return False
    inp=Path(args.input).resolve();stamp=datetime.now().strftime('%Y%m%d_%H%M%S');out=Path(args.output).resolve() if args.output else inp.with_name(inp.stem+f'_교육수료조회_{stamp}.xlsx')
    sn,hr,df=read_input(inp)
    # 엑셀 숫자형으로 추론된 열에도 빈 문자열/문자 결과를 안전하게 기록할 수 있도록
    # 조회 시작 전에 전체 DataFrame을 object 형식으로 변환한다.
    df=df.astype(object)
    all_people=people_from_df(df)
    for c in OUT_COLS:
        if c not in df.columns:
            df[c]=''
        else:
            # 일부 Excel/COM 환경에서 빈 관리 셀이 숫자 544로 읽히는 현상을 제거한다.
            # 관리열에서 544는 유효한 예약/수료 결과가 아니므로 공란으로 정리한다.
            df[c]=df[c].map(lambda v: '' if text(v)=='544' else v)
    normalize_manual_result_rows(df)
    # 퇴사·제외는 제외 상태, 보류는 미수료 상태로 두되 모두 자동 조회 대상에서는 제외한다.
    for p0 in all_people:
        rowp=df.loc[p0.row]
        reason=exclusion_reason(rowp)
        hold=hold_reason(rowp)
        if reason:
            df.at[p0.row,'수료여부']='제외'
            df.at[p0.row,'수료일']=f'조회제외({reason})'
            df.at[p0.row,'구분']='제외'
            df.at[p0.row,'비고']=reason
        elif hold:
            final_date,_=_split_final_completion_and_face_schedule(rowp.get('수료일',''))
            df.at[p0.row,'수료여부']='미수료'
            if final_date: df.at[p0.row,'수료일']=final_date
            df.at[p0.row,'구분']='보류'
            df.at[p0.row,'비고']=hold
    today=date.today()
    initial_state={}
    for p0 in all_people:
        row_initial=df.loc[p0.row]
        key_initial,_,_=row_result_state(row_initial)
        initial_state[p0.row]={
            '이름':p0.name,
            '소속':p0.company,
            '상태':key_initial,
            '교육시청일':requested_training_date(row_initial,p0),
            '수료일':normalize_date(_first_row_text(row_initial,['수료일','수료 일자','수료일자','교육일자']))
        }
    change_regions={}
    def selected(p):
        if args.date_filter!='all' or args.status_filter!='all':
            return row_matches_filters(df.loc[p.row],p,args.date_filter,args.status_filter,today)
        return row_matches_target(df.loc[p.row],p,args.target,today)
    people=[p for p in all_people if selected(p)]
    if args.resume_row >= 0:
        people=[p for p in people if p.row > args.resume_row]
        print(f'RESUME_FROM_ROW|{args.resume_row}|남은대상={len(people)}',flush=True)
    people=people[:args.limit] if args.limit else people
    print(f'SELECTED|{len(people)}|{args.date_filter}:{args.status_filter}' if (args.date_filter!='all' or args.status_filter!='all') else f'SELECTED|{len(people)}|{args.target}',flush=True)
    regions=[x.strip() for x in args.regions.split(',') if x.strip()]
    # In the packaged release the worker lives under ``_internal`` while
    # user-visible results/debug folders belong beside ZeroCool_AI.exe.
    root=(Path(sys.executable).resolve().parent
          if getattr(sys,'frozen',False)
          else Path(__file__).resolve().parent.parent)
    debug=root/'debug'; debug.mkdir(parents=True,exist_ok=True); ai_samples=[]
    if not people:
        write_result(inp,sn,hr,df,out)
        counts=summary_counts(df,all_people);print('SUMMARY|'+json.dumps(counts,ensure_ascii=False),flush=True);print('OUTPUT|'+str(out),flush=True);return
    d=driver_new(False) if args.mode=='completion' else None
    stopped=False
    try:
        for n,p in enumerate(people,1):
            if stop_requested():
                stopped=True
                print(f'STOPPED|{n-1}|{len(people)}|사용자 중지 요청',flush=True)
                break
            try:
                if args.mode=='completion':
                    d,_=ensure_driver(d,False)
                print(f'PROGRESS|{n}|{len(people)}|{p.name}|조회중',flush=True)
                row0=df.loc[p.row]
                bestres=ReservationResult(bool(requested_training_date(row0,p)),text(row0.get('사이트','')),requested_training_date(row0,p),text(row0.get('교육방식','')),text(row0.get('예약상태','')),text(row0.get('교육종류','')),text(row0.get('교육장소','')),text(row0.get('예약조회내용','')))
                bestcomp=CompletionResult(text(row0.get('수료여부','')),text(row0.get('수료일','')),text(row0.get('구분','')),text(row0.get('교육종류','')),text(row0.get('교육장소','')),text(row0.get('수료조회내용','')))
                if args.mode=='all':
                    bestres=ReservationResult();bestcomp=CompletionResult('미수료','','미수료')
                errors=[]
                multi_region_recheck = args.mode=='completion' and len(regions)>1
                reservation_cross_lookup = args.mode in ('all','reservation')
                # 수료조회와 동일하게 예약조회도 UI에서 체크한 지역 순서를 그대로 사용한다.
                # 사람별 사이트/소속이 비어 있어도 체크한 기관을 순차 조회하며, 당해연도 예약 발견 즉시 종료한다.
                assigned_region=region_for_person(row0,p,regions) if regions else ''
                if not regions:
                    msg='조회할 지역이 선택되지 않았습니다.'
                    errors.append(msg)
                    print(f'ERROR|{p.name}|기관선택|입력정보부족: {msg}',flush=True)
                    bestres.site=''
                    bestcomp=CompletionResult('입력정보부족','','입력정보부족',detail=msg,error=msg)
                else:
                    reservation_regions=list(regions) if reservation_cross_lookup else []
                    completion_regions=(list(regions) if multi_region_recheck else [assigned_region or regions[0]])
                    route_regions=completion_regions
                    shown_route=reservation_regions if reservation_cross_lookup else completion_regions
                    print(f'ROUTE|{p.name}|{"+".join(shown_route)}|{args.mode}',flush=True)
                    rr=ReservationResult();cc=CompletionResult()
                    if reservation_cross_lookup:
                        for reservation_region in reservation_regions:
                            one_rr=ReservationResult(site=reservation_region)
                            print(f'REGION_START|{p.name}|{reservation_region}|예약조회',flush=True)
                            for attempt in (1,2):
                                try:
                                    d,_=ensure_driver(d,False)
                                    one_rr=reservation_lookup(d,reservation_region,p,debug,n)
                                    break
                                except (InvalidSessionIdException,NoSuchWindowException) as e:
                                    print(f'SESSION|{p.name}|{reservation_region} 예약|세션끊김 재시도 {attempt}/2',flush=True)
                                    driver_close(d);d=None
                                    if attempt==2:
                                        errors.append(f'{reservation_region} 예약:{type(e).__name__}:{e}')
                                        print(f'ERROR|{p.name}|{reservation_region} 예약|{type(e).__name__}: {e}',flush=True)
                                except Exception as e:
                                    errors.append(f'{reservation_region} 예약:{type(e).__name__}:{e}')
                                    print(f'ERROR|{p.name}|{reservation_region} 예약|{type(e).__name__}: {e}',flush=True)
                                    dump_debug(d,debug,f'{n:04d}_{reservation_region}_예약오류_시도{attempt}')
                                    if attempt==1:
                                        driver_close(d);d=None;time.sleep(.7)
                                        continue
                                    break
                            print(f'REGION_RESULT|{p.name}|{reservation_region}|{one_rr.status or "예약없음"}|{one_rr.reservation_date}',flush=True)
                            if one_rr.found and _completion_year(one_rr.reservation_date)==today.year:
                                bestres=one_rr
                                change_regions[p.row]=reservation_region
                                print(f'SHORT_CIRCUIT|{p.name}|{reservation_region}|당해연도 예약 확인 · 남은 기관 조회 생략',flush=True)
                                break
                            if not bestres.site:
                                bestres.site=reservation_region
                                bestres.status='예약없음'
                                bestres.detail=one_rr.detail
                    if args.mode in ('all','completion'):
                        dual_results=[]
                        for lookup_region in route_regions:
                            # 기관별 처리시간 측정은 조회 시작 직전에 반드시 초기화한다.
                            # 이전 버전에서 이 초기화가 누락되어 첫 기사부터 NameError가 발생했다.
                            region_started=time.time()
                            one=CompletionResult()
                            # 경기·인천 사이트는 개인정보동의/인증 상태가 브라우저 세션에 남을 수 있다.
                            # 다른 기사 조회 시 반드시 완전히 새 Chrome 세션을 사용하고 조회 후 즉시 종료한다.
                            # 서울은 기존 메인 Chrome을 계속 사용한다.
                            lookup_driver = None
                            try:
                                for attempt in (1,2):
                                    try:
                                        if lookup_region in ('경기','인천'):
                                            driver_close(lookup_driver)
                                            lookup_driver=driver_new(False)
                                            print(f'SESSION|{p.name}|{lookup_region} 수료|기사별 새 Chrome 세션 시작 {attempt}/2',flush=True)
                                            one=completion_lookup(lookup_driver,lookup_region,p,debug,n)
                                        else:
                                            d,_=ensure_driver(d,False)
                                            one=completion_lookup(d,lookup_region,p,debug,n)
                                        break
                                    except (InvalidSessionIdException,NoSuchWindowException) as e:
                                        print(f'SESSION|{p.name}|{lookup_region} 수료|세션끊김 재시도 {attempt}/2',flush=True)
                                        if lookup_region in ('경기','인천'):
                                            driver_close(lookup_driver); lookup_driver=None
                                        else:
                                            driver_close(d); d=None
                                        if attempt==2:
                                            errors.append(f'{lookup_region} 수료:{type(e).__name__}:{e}')
                                            print(f'ERROR|{p.name}|{lookup_region} 수료|{type(e).__name__}: {e}',flush=True)
                                            one=CompletionResult('미수료','조회오류','조회오류',error=str(e))
                                    except Exception as e:
                                        errors.append(f'{lookup_region} 수료:{type(e).__name__}:{e}')
                                        print(f'ERROR|{p.name}|{lookup_region} 수료|{type(e).__name__}: {e}',flush=True)
                                        dump_debug(lookup_driver if lookup_region in ('경기','인천') else d,debug,f'{n:04d}_{lookup_region}_수료오류_시도{attempt}')
                                        if attempt==1:
                                            print(f'SESSION|{p.name}|{lookup_region} 수료|새 Chrome 세션으로 재시도 2/2',flush=True)
                                            if lookup_region in ('경기','인천'):
                                                driver_close(lookup_driver); lookup_driver=None
                                            else:
                                                driver_close(d); d=None
                                            time.sleep(1)
                                            continue
                                        one=CompletionResult('미수료','조회오류','조회오류',error=str(e))
                                        break
                            finally:
                                if lookup_region in ('경기','인천'):
                                    driver_close(lookup_driver)
                                    print(f'SESSION|{p.name}|{lookup_region} 수료|기사별 Chrome 세션 종료',flush=True)
                            elapsed_region=max(time.time()-region_started,0.0)
                            ai_samples.append({'region':lookup_region,'seconds':elapsed_region,'success':bool(one.status=='교육수료' and _completion_year(one.completion_date)==today.year),'error':bool(one.category=='조회오류')})
                            print(f'AI_METRIC|{lookup_region}|{elapsed_region:.2f}|{one.category or one.status}',flush=True)
                            dual_results.append((lookup_region,one))
                            print(f'REGION_RESULT|{p.name}|{lookup_region}|{one.status}|{one.category}|{one.completion_date}',flush=True)
                            # 당해연도 수료가 확인되면 법정교육 수료 판정이 확정되므로 남은 기관 조회를 생략한다.
                            if one.status=='교육수료' and _completion_year(one.completion_date)==today.year:
                                print(f'SHORT_CIRCUIT|{p.name}|{lookup_region}|당해연도 수료 확인 · 남은 기관 조회 생략',flush=True)
                                break
                        if multi_region_recheck:
                            matched_region,bestcomp=merge_multi_completion(dual_results)
                            bestres.site=matched_region
                        else:
                            bestcomp=dual_results[0][1]
                            if not bestres.site:
                                bestres.site=route_regions[0]
                # 인천 등 다른 기관에서 이미 확인해 둔 당해연도 수료 기록도 유효하다.
                # 서울/경기/인천 조회가 결과없음 또는 과거 이력만 반환해도 기존 당해연도 수료를 덮어쓰지 않는다.
                existing_date=_first_row_text(row0,['수료일','수료 일자','수료일자','교육일자'])
                existing_status=canonical_completion_status(_first_row_text(row0,['수료여부','수료 여부','수료결과','교육수료여부']))
                if _completion_year(existing_date)==today.year and existing_status=='교육수료' and _completion_year(bestcomp.completion_date)!=today.year:
                    bestcomp=CompletionResult('교육수료',existing_date,'교육수료',text(row0.get('교육종류','')),text(row0.get('교육장소','')),text(row0.get('수료조회내용','')))

                # 수료조회 화면에 예약/예정일이 함께 표시된 경우에만 예약일을 보완한다.
                # 확인되지 않으면 사용자가 입력한 기존 교육시청일을 그대로 유지한다.
                # 수료조회와 예약조회는 완전히 분리한다.
                # 수료조회 화면에 예정일이 보여도 교육시청일/예약일은 변경하지 않는다.
                discovered_from_completion=''
                discovered_region=''
                rdate=bestres.reservation_date or requested_training_date(row0,p)
                if args.mode=='reservation':
                    online_date=online_training_date(row0,bestres,bestres.site or (route_regions[0] if route_regions else ''))
                    online_obj=date_obj(online_date)
                    # 실제 예약조회 결과에서 확인된 당해연도 미래 예약만 교육시청일을 변경한다.
                    if bestres.found and online_obj and online_obj.year==today.year and online_obj>today:
                        rdate=online_date
                    else:
                        online_date=''
                else:
                    online_date=discovered_from_completion
                    if discovered_from_completion:
                        rdate=discovered_from_completion
                rd=date_obj(rdate)
                pending_note=''
                clear_face_schedule=False
                if rd and rd>today and bestcomp.status!='교육수료':
                    previous_completion=normalize_date(bestcomp.completion_date) or normalize_date(existing_date)
                    is_online=_is_online_training(row0,bestres,bestres.site or (route_regions[0] if route_regions else ''))
                    bestcomp.status='미수료'
                    # 수료일에는 실제 최종 수료일만 보존한다. 예정일은 교육시청일 또는 비고에서 관리한다.
                    bestcomp.completion_date=previous_completion
                    if is_online:
                        bestcomp.category='입교예정'
                    else:
                        bestcomp.category='미수료'
                        pending_note=f'대면교육 입교예정일 {rdate}'
                        clear_face_schedule=True
                elif rd and rd<=today and bestcomp.status!='교육수료':
                    # 미래였던 입교예정일이 지나면 당해연도 수료가 확인되지 않는 한 미수료로 재판정한다.
                    bestcomp.status='미수료'
                    if bestcomp.category not in ('조회오류','입력정보부족','예약확인필요','정보변경확인'):
                        bestcomp.category='미수료'
                    bestcomp.completion_date=normalize_date(bestcomp.completion_date) or normalize_date(existing_date)
                elif bestcomp.status=='':
                    bestcomp.status='미수료';bestcomp.category='결과없음'
                i=p.row
                vals={'최종조회일시':datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                if args.mode=='reservation':
                    vals.update({'예약일':rdate,'교육방식':bestres.method,'사이트':bestres.site,'예약상태':bestres.status or ('예약없음' if not bestres.found else ''),'예약조회내용':bestres.detail or ('; '.join(errors) if errors else '')})
                    if online_date:
                        vals['교육시청일']=month_day_display(online_date) or online_date
                if args.mode=='completion':
                    vals.update({'수료여부':bestcomp.status,'수료일':bestcomp.completion_date,'구분':bestcomp.category,'교육종류':bestcomp.course or bestres.course,'교육장소':bestcomp.place or bestres.place,'수료조회내용':bestcomp.detail or bestcomp.error})
                    # 당해연도 수료자는 예약일이 아니라 실제 수료일을 교육시청일에 표시한다.
                    # 신청양식 표기와 동일하게 M/D 형식을 사용한다.
                    if bestcomp.status=='교육수료' and _completion_year(bestcomp.completion_date)==today.year:
                        completed_md=month_day_display(bestcomp.completion_date)
                        if completed_md:
                            old_training_md=month_day_display(_first_row_text(row0,['교육시청일','교육 시청일','예정일','예약일','교육일','시청일']))
                            vals['교육시청일']=completed_md
                            # 실제 수료일이 기존 예약기수 일정과 다르면 기수 정보는 더 이상 유효하지 않다.
                            if old_training_md and old_training_md!=completed_md:
                                vals['기수']=''
                            special_note=completion_training_note(bestcomp)
                            if special_note:
                                vals['비고']=_append_note(row0,special_note)
                if pending_note:
                    if '비고' not in df.columns: df['비고']=''
                    vals['비고']=_append_note(row0,pending_note)
                # 보류·제외를 명시적으로 조회한 경우 관리 상태는 자동 해제하지 않는다.
                original_exclusion=exclusion_reason(row0)
                original_hold=hold_reason(row0)
                if original_exclusion:
                    vals['수료여부']='제외'; vals['구분']='제외'
                    vals['비고']=_append_note(row0,f'{today:%Y-%m-%d} 조회결과: {bestcomp.status} {bestcomp.completion_date}'.strip())
                elif original_hold:
                    vals['수료여부']='미수료'; vals['구분']='보류'
                    vals['비고']=_append_note(row0,f'{today:%Y-%m-%d} 조회결과: {bestcomp.status} {bestcomp.completion_date}'.strip())
                for k,v in vals.items():
                    if k not in df.columns:
                        df[k]=pd.Series(['']*len(df),index=df.index,dtype=object)
                    elif df[k].dtype != object:
                        df[k]=df[k].astype(object)
                    df.at[i,k]=v
                save_query(p,bestres,bestcomp,row_fingerprint(df.loc[i]))
                if args.mode=='reservation':
                    print(f'RESULT|{p.name}|예약조회|{bestres.status or "예약없음"}|{rdate}|{bestres.site}',flush=True)
                else:
                    print(f'RESULT|{p.name}|{bestcomp.status}|{bestcomp.category}|{rdate}|{bestres.site}',flush=True)
                # 기사 1명 완료 때마다 현재 결과를 저장해 강제 종료 시 재조회 범위를 최소화한다.
                try:
                    out.parent.mkdir(parents=True,exist_ok=True)
                    write_result(inp,sn,hr,df,out)
                    print(f'CHECKPOINT|{n}|{len(people)}|{p.row}|{out}',flush=True)
                except Exception as checkpoint_error:
                    print(f'ERROR|체크포인트저장|{type(checkpoint_error).__name__}: {checkpoint_error}',flush=True)
            except Exception as person_error:
                # 한 기사 또는 한 행에서 예상하지 못한 오류가 발생해도 전체 조회를 중단하지 않는다.
                # 오류 기사만 조회오류로 표시하고 다음 기사 조회를 계속한다.
                person_trace=traceback.format_exc()
                error_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                error_summary=f'{type(person_error).__name__}: {person_error}'
                try:
                    i=p.row
                    current_status=canonical_completion_status(text(df.at[i,'수료여부']))
                    current_date=text(df.at[i,'수료일'])
                    # 예약조회 오류는 수료여부·수료일·구분을 절대 변경하지 않는다.
                    if args.mode=='completion':
                        if not (_completion_year(current_date)==today.year and current_status=='교육수료'):
                            df.at[i,'수료여부']='미수료'
                            df.at[i,'구분']='조회오류'
                        df.at[i,'수료조회내용']=error_summary
                    else:
                        df.at[i,'예약상태']='조회오류'
                        df.at[i,'예약조회내용']=error_summary
                    df.at[i,'최종조회일시']=error_time
                    if '비고' in df.columns:
                        df.at[i,'비고']=_append_note(df.loc[i],f'자동조회 오류: {error_summary}')
                except Exception:
                    pass
                debug.mkdir(parents=True,exist_ok=True)
                person_error_file=debug/f'기사별오류_{n:04d}_{p.name}_{stamp}.txt'
                try:
                    person_error_file.write_text(person_trace,encoding='utf-8')
                except Exception:
                    pass
                print(f'ERROR|{p.name}|기사처리|{error_summary}',flush=True)
                print(f'PERSON_ERROR_LOG|{p.name}|{person_error_file}',flush=True)
                try:
                    out.parent.mkdir(parents=True,exist_ok=True)
                    write_result(inp,sn,hr,df,out)
                    print(f'CHECKPOINT|{n}|{len(people)}|{p.row}|{out}|오류후저장',flush=True)
                except Exception as checkpoint_error:
                    print(f'ERROR|오류후저장|{type(checkpoint_error).__name__}: {checkpoint_error}',flush=True)
                driver_close(d); d=None
                continue
    except Exception:
        # 조회 도중 오류가 나도 그 시점까지의 결과와 전체 오류내역을 반드시 보존한다.
        err_text=traceback.format_exc()
        debug.mkdir(parents=True,exist_ok=True)
        error_file=debug/f'오류내역_{stamp}.txt'
        try:
            error_file.write_text(err_text,encoding='utf-8')
        except Exception:
            pass
        try:
            out.parent.mkdir(parents=True,exist_ok=True)
            write_result(inp,sn,hr,df,out)
            print(f'PARTIAL_OUTPUT|{out}',flush=True)
        except Exception as save_error:
            try:
                with error_file.open('a',encoding='utf-8') as f:
                    f.write('\n\n[부분 결과 저장 오류]\n'+traceback.format_exc())
            except Exception:
                pass
            print(f'ERROR|부분결과저장|{type(save_error).__name__}: {save_error}',flush=True)
        print(f'ERROR_LOG|{error_file}',flush=True)
        raise
    finally:
        driver_close(d)
    write_result(inp,sn,hr,df,out)
    # 기관별 조회 성능을 로컬에 누적하여 다음 실행의 AI 추천순서에 반영한다.
    try:
        stats_path=root/'ai_region_stats.json'
        old_stats=json.loads(stats_path.read_text(encoding='utf-8')) if stats_path.exists() else {}
        for region_name in ('서울','경기','인천'):
            samples=[x for x in ai_samples if x['region']==region_name]
            if not samples:
                continue
            prev=old_stats.get(region_name,{})
            prev_n=int(prev.get('samples',0) or 0); add_n=len(samples); total=prev_n+add_n
            avg_new=sum(x['seconds'] for x in samples)/add_n
            success_new=sum(1 for x in samples if x['success'])/add_n
            error_new=sum(1 for x in samples if x['error'])/add_n
            old_stats[region_name]={
                'samples':total,
                'avg_seconds':((float(prev.get('avg_seconds',0) or 0)*prev_n)+(avg_new*add_n))/total,
                'current_year_success_rate':((float(prev.get('current_year_success_rate',0) or 0)*prev_n)+(success_new*add_n))/total,
                'error_rate':((float(prev.get('error_rate',0) or 0)*prev_n)+(error_new*add_n))/total,
                'updated_at':datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        stats_path.write_text(json.dumps(old_stats,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'AI_STATS|{stats_path}',flush=True)
    except Exception as ai_error:
        print(f'ERROR|AI통계저장|{type(ai_error).__name__}: {ai_error}',flush=True)
    changes=[]
    for p0 in all_people:
        before=initial_state.get(p0.row,{})
        after_row=df.loc[p0.row]
        after_key,_,_=row_result_state(after_row)
        after_training=requested_training_date(after_row,p0)
        after_completion=normalize_date(_first_row_text(after_row,['수료일','수료 일자','수료일자','교육일자']))
        reason=status_change_reason(before.get('상태',''),after_key,before.get('교육시청일',''),after_training,change_regions.get(p0.row,''))
        if reason or before.get('수료일','')!=after_completion:
            changes.append({
                '조회일시':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                '소속':before.get('소속',''),
                '이름':before.get('이름',p0.name),
                '이전상태':before.get('상태',''),
                '변경상태':after_key,
                '이전교육시청일':before.get('교육시청일',''),
                '변경교육시청일':after_training,
                '이전수료일':before.get('수료일',''),
                '변경수료일':after_completion,
                '변경사유':reason or '수료일 변경'
            })
    try:
        log_path=write_change_log(out,changes)
        if log_path:
            print(f'CHANGE_LOG|{log_path}|{len(changes)}',flush=True)
    except Exception as log_error:
        print(f'ERROR|상태변경로그저장|{type(log_error).__name__}: {log_error}',flush=True)
    counts=summary_counts(df,all_people);print('SUMMARY|'+json.dumps(counts,ensure_ascii=False),flush=True);print('OUTPUT|'+str(out),flush=True)
    if stopped:
        sys.exit(2)
if __name__=='__main__':
    try:main()
    except Exception:
        traceback.print_exc();sys.exit(1)
