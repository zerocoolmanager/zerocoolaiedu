from __future__ import annotations
import json, os, queue, subprocess, sys, threading, time
from datetime import datetime, date
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3
import pandas as pd
from launcher_ui import (
    BG, BLUE, DANGER, FONT_KR, SURFACE, TEXT, TEXT_MUTED, WHITE,
    apply_dashboard_styles, apply_windows_chrome, build_dashboard_ui,
)

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
RESULTS_DIR = ROOT / 'results'
DEBUG_DIR = ROOT / 'debug'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('ZeroCool AI · 서울·경기·인천 보수교육 관리 v15.0.3')
        self.geometry('1280x820'); self.minsize(1080,720)
        self.configure(bg=BG)
        self.q=queue.Queue(); self.proc=None; self.output=''; self.pending_followup=None; self.vars={}; self.date_filter=tk.StringVar(value='due'); self.status_vars={k:tk.BooleanVar(value=True) for k in ('completed','incomplete','scheduled','hold','excluded','error')}; self.status_all=tk.BooleanVar(value=True); self.last_error=''; self.rows=[]; self.current_filter='전체'; self.control_file=None; self.stop_requested=False; self.last_run=None; self.run_started_at=None; self.error_count=0; self.region_metrics={}; self.before_snapshot={}; self.last_changes=[]; self.last_elapsed=0; self.selected_run_total=0; self.query_vars={'completion':tk.BooleanVar(value=True),'reservation':tk.BooleanVar(value=True)}; self.query_all=tk.BooleanVar(value=True)
        self._styles(); self._ui(); self.after(0,self._apply_windows_chrome); self.after(100,self._poll)

    def _apply_windows_chrome(self):
        apply_windows_chrome(self)

    def _styles(self):
        apply_dashboard_styles(self)

    def _ui(self):
        build_dashboard_ui(self)

    def run_reservation_separate(self, target='all'):
        msg=(
            '예약조회는 수료조회와 완전히 분리되어 실행됩니다.\n\n'
            '· 예약조회 오류가 나도 수료여부와 수료일은 변경되지 않습니다.\n'
            '· 기존 교육시청일은 삭제하지 않습니다.\n'
            '· 체크한 지역 순서대로 올해 예약만 확인합니다.\n'
            '· 예약이 확인되면 남은 지역 조회를 즉시 중단합니다.\n'
            '· 예약이 없으면 기존 교육시청일을 유지합니다.\n\n'
            '예약조회를 시작하시겠습니까?'
        )
        if not messagebox.askyesno('예약조회 별도 실행',msg):
            return
        self.run('reservation',target)

    def show_more_actions(self):
        win=tk.Toplevel(self);win.title('더보기');win.geometry('500x410+30+90');win.transient(self);win.configure(bg=WHITE)
        frame=ttk.Frame(win,padding=14);frame.pack(fill='both',expand=True)
        actions=[
            ('전체 미수료 재조회',lambda:self.run('completion','incomplete_all')),
            ('수료일 공란만 조회',lambda:self.run('completion','completion_blank')),
            ('결과없음 재조회',lambda:self.run('completion','noresult')),
            ('3명 테스트',lambda:self.run('completion','all',3)),
            ('조회오류 재조회',lambda:self.run('completion','error')),
            ('AI 조회 분석',self.show_ai_report),
            ('입력정보부족 재확인',lambda:self.run('completion','input_missing')),
            ('미조회자만 조회',lambda:self.run('completion','unqueried')),
            ('저장 폴더 열기',self.open_folder),('오류 진단 보기',self.show_error),
            ('debug 폴더 열기',self.open_debug),('오늘 변경내역 보기',self.show_changes),
            ('전체 명단 보기',lambda:self.apply_status_filter('전체')),
            ('예약조회 별도 실행',self.run_reservation_separate),
        ]
        for i,(txt,cmd) in enumerate(actions):
            ttk.Button(frame,text=txt,style='ZC.TButton',command=lambda c=cmd:(c(),win.destroy())).grid(row=i//2,column=i%2,sticky='ew',padx=4,pady=4)
        frame.columnconfigure(0,weight=1);frame.columnconfigure(1,weight=1)
        ttk.Button(frame,text='닫기',style='ZC.TButton',command=win.destroy).grid(row=8,column=0,columnspan=2,sticky='ew',padx=4,pady=(12,4))

    def show_changelog(self):
        messagebox.showinfo(
            'v15.0.3 주요 변경사항',
            '· 서울 예약: edu.tredu.kr 교육 예약확인 및 변경 적용\n'
            '· 경기: 예약 확인 및 취소 페이지 적용\n'
            '· 인천: 집합교육 예약확인 페이지 및 010 자동 선택\n'
            '· 체크한 지역 순서대로 당해연도 예약 교차조회\n'
            '· 예약 확인 즉시 남은 지역 조회 생략\n'
            '· 예약이 없으면 기존 교육시청일 유지\n'
            '· 기존 수료조회, 대시보드, 변경로그 유지'
        )

    def pick(self):
        p=filedialog.askopenfilename(filetypes=[('Excel 파일','*.xls *.xlsx')])
        if p:self.file.set(p);self.refresh_file()

    def _classify_df(self,df):
        counts={k:0 for k in self.vars}; rows=[]
        try:
            from unified_checker import people_from_df, text, row_result_state, exclusion_reason, requested_training_date, normalize_manual_result_rows
            normalize_manual_result_rows(df)
            people=people_from_df(df); counts['전체']=len(people)
            for p in people:
                row=df.loc[p.row]
                key,status,cat=row_result_state(row)
                rdate=requested_training_date(row,p)
                # row_result_state가 최종수료연도/미래 교육시청일/보류·제외를 한 기준으로 판정한다.
                reason=exclusion_reason(row)
                site=text(row.get('사이트',''))
                counts[key]=counts.get(key,0)+1
                # 결과없음·조회오류 등은 미수료 총계에 포함하면서 세부 숫자도 함께 표시한다.
                if key=='미수료' and cat in ('보류','예약확인필요','정보변경확인','결과없음','조회오류','입력정보부족'):
                    
                    # 세부 상태 카드가 없는 경우에도 파일 분석이 중단되지 않도록 안전 집계
                    if cat in counts:
                        counts[cat]=counts.get(cat,0)+1
                display_status=status or ('미수료' if key in ('입교예정','미수료') else key if key in ('보류','제외') else '')
                note=reason or text(row.get('비고',''))
                display_cat=('제외' if key=='제외' else (cat or key))
                rows.append((p.name,display_status,text(row.get('수료일','')),display_cat,rdate,site,note))
        except Exception as e:
            raise RuntimeError(f'파일 현황 분석 실패: {e}') from e
        return counts,rows

    def refresh_file(self):
        p=self.file.get().strip()
        if not p or not Path(p).exists():
            self.header_status.set('조회 파일을 선택해 주세요.'); return
        try:
            from unified_checker import read_input
            _,_,df=read_input(Path(p))
            counts,self.rows=self._classify_df(df)
            for k,v in counts.items(): self.vars[k].set(str(v))
            self.current_filter='전체'; self.filter_label.set('전체 명단'); self.render_rows()
            self.header_status.set(f'선택됨: {Path(p).name} · 전체 {counts["전체"]}명')
            err=int(counts.get('조회오류',0)); inc=int(counts.get('미수료',0)); sch=int(counts.get('입교예정',0))
            if err>0:
                self.alert_var.set(f'❗ 확인 필요 · 조회오류 {err}명 — 오류 재조회를 먼저 진행해 주세요.')
                self.alert_bar.configure(bg='#ffe8e8',fg='#b4232c')
            elif inc>0:
                self.alert_var.set(f'⚠ 확인 필요 · 미수료 {inc}명 · 입교예정 {sch}명 — 대상자를 확인해 주세요.')
                self.alert_bar.configure(bg='#fff4cf',fg='#8a5a00')
            else:
                self.alert_var.set('✓ 확인 완료 · 현재 조회오류나 미수료 대상이 없습니다.')
                self.alert_bar.configure(bg='#e8f7ef',fg='#16764b')
            self.ptext.set('파일 현황을 불러왔습니다.'); self.update_target_preview()
        except Exception as e:
            self.header_status.set(f'파일 분석 오류: {Path(p).name}')
            messagebox.showerror('파일 분석 오류',str(e))

    def run(self,mode,target='all',limit=0,date_filter=None,status_filter=None):
        if self.proc:return messagebox.showwarning('실행 중','현재 조회가 진행 중입니다.')
        if mode=='all':
            # 수료와 예약은 한 프로세스에서 섞지 않고 수료 완료 후 예약을 별도 실행한다.
            self.pending_followup=('reservation',target,limit,date_filter,status_filter)
            mode='completion'
        elif self.pending_followup is None:
            self.pending_followup=None
        p=self.file.get().strip()
        if not p or not Path(p).exists():return messagebox.showerror('파일 필요','유효한 신청 양식을 선택하세요.')
        target_labels={
            'all':'전체 명단','due':'오늘까지 도래자','scheduled_completion':'입교예정',
            'incomplete':'미수료(입교예정 제외·서울+경기+인천)','incomplete_all':'전체 미수료(서울+경기+인천)','completion_blank':'수료일 공란',
            'noresult':'결과없음','error':'조회오류','input_missing':'입력정보부족','unqueried':'미조회자'
        }
        try:
            from unified_checker import read_input, count_target_rows
            _,_,preview_df=read_input(Path(p))
            self.before_snapshot=self._make_snapshot(preview_df)
            if date_filter is not None or status_filter is not None:
                from unified_checker import count_filter_rows
                target_count=count_filter_rows(preview_df,date_filter or 'all',status_filter or 'all')
            else:
                target_count=count_target_rows(preview_df,target)
        except Exception as e:
            return messagebox.showerror('대상 확인 오류',f'조회 대상을 확인하지 못했습니다.\n{e}')
        if target_count<=0:
            try:
                reason=self._zero_target_reason(preview_df,date_filter or 'all',status_filter or 'all',target_count)
            except Exception:
                reason='현재 선택한 조건에 해당하는 기사님이 없습니다.'
            condition=(f'날짜: {self._date_label(date_filter or "all")}\n상태: {self._status_label(status_filter or "all")}'
                       if date_filter is not None or status_filter is not None else target_labels.get(target,target))
            return messagebox.showinfo('조회 대상 없음',f'현재 조건의 조회 대상은 0명입니다.\n\n{condition}\n\n원인\n{reason}')
        if not limit and (target!='all' or date_filter is not None or status_filter is not None):
            label=(f"{self._date_label(date_filter or 'all')} · {self._status_label(status_filter or 'all')}" if date_filter is not None or status_filter is not None else target_labels.get(target,target))
            if not messagebox.askyesno('조회 확인',f'{label} 조건으로 {target_count}명을 조회합니다.\n계속하시겠습니까?'):
                return
        # 수료조회는 서울·경기·인천을 교차 확인한다. 체크된 기관은 우선순위로 사용한다.
        selected=[]
        if self.seoul.get(): selected.append('서울')
        if self.gg.get(): selected.append('경기')
        if self.incheon.get(): selected.append('인천')
        if not selected:
            return messagebox.showerror('기관 필요','우선 조회할 기관을 한 곳 이상 선택하세요.')
        all_regions=['서울','경기','인천']
        if mode=='completion':
            remaining=[r for r in all_regions if r not in selected]
            if self.ai_priority.get():
                stats=self._load_ai_stats()
                def score(r):
                    x=stats.get(r,{})
                    success=float(x.get('current_year_success_rate',0) or 0)
                    avg=float(x.get('avg_seconds',999) or 999)
                    return success*100-(avg/10)
                # 한 곳만 체크하면 그 기관은 반드시 첫 번째. 두 곳 이상은 선택 그룹 안에서 학습 점수로 정렬한다.
                first=selected if len(selected)==1 else sorted(selected,key=score,reverse=True)
                remaining=sorted(remaining,key=score,reverse=True)
                regs=first+remaining
                self._log('[AI 추천순서] '+ ' → '.join(regs))
            else:
                regs=selected + remaining
                self._log('[조회순서] '+ ' → '.join(regs))
            self._log('[시간단축] 당해연도 수료가 확인되면 남은 기관 조회는 생략합니다.')
        else:
            regs=selected
        self.log.delete('1.0','end'); self.output=''; self.last_error=''; self.pb['value']=0; self.stop_requested=False; self.resume_btn.configure(state='disabled'); self.run_started_at=time.time(); self.error_count=0; self.region_metrics={}; self.before_snapshot={}; self.last_changes=[]; self.last_elapsed=0; self.selected_run_total=0
        # 중요: 조회 시작 때 query_vars를 새 BooleanVar로 교체하면 화면 버튼과 내부 상태 연결이 끊어진다.
        # 기존 변수를 그대로 유지하여 예약조회 단독 선택이 completion으로 바뀌지 않도록 한다.
        self.ptext.set(f'{target_labels.get(target,target)} {min(target_count,limit) if limit else target_count}명 조회 준비 중')
        self._log(f'[대상선별] {target_labels.get(target,target)} · {target_count}명')
        self._log(f'[조회모드] {mode}')
        if mode=='reservation':
            self._log('[안전확인] 예약조회 전용 모드 · 수료조회 URL 사용 안 함')
        elif mode=='completion':
            self._log('[안전확인] 수료조회 전용 모드 · 예약조회 로직 사용 안 함')
        self._log('[브라우저] '+('백그라운드 작은 창 모드' if self.background_mode.get() else '일반 표시 모드'))
        stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
        out_name=Path(p).stem + f'_교육수료조회_{stamp}.xlsx'
        out_path=RESULTS_DIR / out_name
        cmd=[sys.executable,str(BASE/'unified_checker.py'),p,'--regions',','.join(regs),'--mode',mode,'--target',target,'--browser-mode',('background' if self.background_mode.get() else 'normal'),'--output',str(out_path)]
        if date_filter is not None or status_filter is not None:
            cmd += ['--date-filter',date_filter or 'all','--status-filter',status_filter or 'all']
        if limit:
            test_out=str(RESULTS_DIR / (Path(p).stem+f'_3명테스트_{stamp}.xlsx')); cmd += ['--limit',str(limit),'--output',test_out]
            kind='수료' if mode=='completion' else ('예약' if mode=='reservation' else '통합')
            self._log(f'[3명 {kind} 테스트] 조건에 맞는 대상자 중 앞 3명만 조회합니다.')
        self.control_file=Path(os.environ.get('TEMP',str(BASE)))/f'zerocool_stop_{os.getpid()}_{datetime.now().strftime("%H%M%S%f")}.txt'
        try:self.control_file.unlink(missing_ok=True)
        except Exception:pass
        cmd += ['--control-file',str(self.control_file)]
        self.last_run=(mode,target,limit,date_filter,status_filter)
        env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['PYTHONUTF8']='1'
        self.header_status.set('조회 진행 중입니다...')
        def worker():
            try:
                self.proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=env,cwd=str(BASE))
                for line in self.proc.stdout:self.q.put(line.rstrip())
                code=self.proc.wait();self.q.put(('DONE',code))
            except Exception as e:self.q.put(f'ERROR|프로그램 실행|{type(e).__name__}|{e}');self.q.put(('DONE',1))
            finally:self.proc=None
        threading.Thread(target=worker,daemon=True).start()

    def _date_label(self,value):
        return {'all':'전체 날짜','due':f'오늘까지 ({date.today():%Y-%m-%d})'}.get(value,value)

    def _selected_statuses(self):
        values=[k for k,v in self.status_vars.items() if v.get()]
        return 'all' if len(values)==len(self.status_vars) else ','.join(values)

    def _status_label(self,value=None):
        value=self._selected_statuses() if value is None else value
        mapping={'completed':'수료','incomplete':'미수료','scheduled':'입교예정','hold':'보류','excluded':'제외','error':'조회오류'}
        if value=='all': return '전체 상태'
        vals=[x for x in str(value).split(',') if x]
        return ' + '.join(mapping.get(x,x) for x in vals) if vals else '선택 없음'

    def toggle_all_statuses(self):
        flag=self.status_all.get()
        for v in self.status_vars.values(): v.set(flag)
        self.update_target_preview()

    def on_status_changed(self):
        # 날짜 조건은 사용자가 선택한 값을 그대로 유지한다.
        # 상태 변경 때문에 '오늘까지'/'전체 날짜'가 자동으로 바뀌지 않는다.
        self.status_all.set(all(v.get() for v in self.status_vars.values()))
        self.update_target_preview()

    def toggle_all_statuses_button(self):
        flag=not all(v.get() for v in self.status_vars.values())
        self.status_all.set(flag)
        for v in self.status_vars.values(): v.set(flag)
        self.update_target_preview()

    def toggle_all_queries_button(self):
        flag=not all(v.get() for v in self.query_vars.values())
        self.query_all.set(flag)
        for v in self.query_vars.values(): v.set(flag)
        self.on_query_changed()

    def on_query_changed(self):
        selected=[k for k,v in self.query_vars.items() if v.get()]
        self.query_all.set(len(selected)==len(self.query_vars))
        if selected==['completion']:
            self.query_note.set('수료 여부만 확인합니다.')
        elif selected==['reservation']:
            self.query_note.set('예약 일정만 확인합니다. 기존 수료 결과는 변경하지 않습니다.')
        elif len(selected)==2:
            self.query_note.set('수료조회 → 예약조회 순서로 자동 진행됩니다.')
        else:
            self.query_note.set('조회 항목을 한 개 이상 선택해 주세요.')
        self.update_target_preview()

    def _selected_query_mode(self):
        completion=self.query_vars['completion'].get()
        reservation=self.query_vars['reservation'].get()
        if completion and reservation: return 'all'
        if completion: return 'completion'
        if reservation: return 'reservation'
        return ''

    def _set_statuses(self,values):
        values=set(values)
        for k,v in self.status_vars.items(): v.set(k in values)
        self.status_all.set(len(values)==len(self.status_vars))

    def apply_preset(self,key):
        if key=='today':
            self.date_filter.set('due'); self._set_statuses(self.status_vars.keys())
        elif key=='allcheck':
            self.date_filter.set('all'); self._set_statuses(self.status_vars.keys())
        elif key in self.status_vars:
            # 상태 프리셋도 현재 날짜 조건을 보존한다.
            self._set_statuses([key])
        self.update_target_preview()

    def update_target_preview(self):
        p=self.file.get().strip(); statuses=self._selected_statuses()
        qmode=self._selected_query_mode()
        qlabel={'completion':'수료조회','reservation':'예약조회','all':'수료+예약조회','':'선택 없음'}.get(qmode,qmode)
        label=f"{self._date_label(self.date_filter.get())} · {self._status_label(statuses)} · {qlabel}"
        if not p or not Path(p).exists():
            self.target_preview.set(f'조회 조건: {label}\n파일을 선택하면 대상 인원을 표시합니다.')
            return
        if not statuses:
            self.target_preview.set(f'조회 조건: {label}\n상태를 한 개 이상 선택해 주세요.')
            return
        if not qmode:
            self.target_preview.set(f'조회 조건: {label}\n조회 항목을 한 개 이상 선택해 주세요.')
            return
        try:
            from unified_checker import read_input, count_filter_rows
            _,_,df=read_input(Path(p)); n=count_filter_rows(df,self.date_filter.get(),statuses)
            selected=set(statuses.split(',')) if statuses!='all' else set(self.status_vars)
            warning='\n※ 보류·제외는 기존 관리 상태를 유지하고 조회 결과만 기록합니다.' if selected & {'hold','excluded'} else ''
            # 복수 상태 선택 시 상태별 인원과 합계를 함께 보여 직원이 조회대상을 즉시 검증할 수 있게 한다.
            detail=[]
            order=[('completed','수료'),('incomplete','미수료'),('scheduled','입교예정'),('hold','보류'),('excluded','제외'),('error','조회오류')]
            if statuses!='all':
                for code,name in order:
                    if code in selected:
                        cnt=count_filter_rows(df,self.date_filter.get(),code)
                        detail.append(f'{name} {cnt}명')
            detail_text=(' · '.join(detail)+' = ' if detail else '')
            reason=self._zero_target_reason(df,self.date_filter.get(),statuses,n)
            if reason:
                warning += f'\n⚠ {reason}'
            self.target_preview.set(f'조회 조건: {label}\n조회 대상: {detail_text}{n}명{warning}')
        except Exception as e:
            self.target_preview.set(f'조회 조건: {label}\n대상 계산 오류: {e}')


    def _zero_target_reason(self,df,date_filter,statuses,current_count):
        """현재 조건이 0명일 때 날짜/상태 조합의 원인을 설명한다."""
        if current_count or date_filter!='due':
            return ''
        try:
            from unified_checker import count_filter_rows, people_from_df, row_matches_filters, requested_training_date, date_obj
            all_date_count=count_filter_rows(df,'all',statuses)
            if all_date_count<=0:
                return '선택한 상태에 해당하는 대상자가 없습니다.'
            today=date.today()
            future=0; no_date=0
            for person in people_from_df(df):
                row=df.loc[person.row]
                if not row_matches_filters(row,person,'all',statuses,today):
                    continue
                rd=date_obj(requested_training_date(row,person))
                if rd and rd>today:
                    future+=1
                elif not rd:
                    no_date+=1
            parts=[]
            if future:
                parts.append(f'오늘 이후 일정 {future}명')
            if no_date:
                parts.append(f'교육시청일 미입력 {no_date}명')
            detail=' · '.join(parts)
            if detail:
                return f'선택 상태 대상은 전체 날짜 기준 {all_date_count}명이지만, 오늘까지 조건에서 제외되었습니다. ({detail})'
            return f'선택 상태 대상은 전체 날짜 기준 {all_date_count}명이지만, 오늘까지 조건에 해당하지 않습니다.'
        except Exception:
            return '현재 날짜·상태 조건에 해당하는 대상자가 없습니다.'

    def run_filtered(self):
        statuses=self._selected_statuses()
        if not statuses:
            return messagebox.showwarning('상태 선택','조회할 상태를 한 개 이상 선택하세요.')
        mode=self._selected_query_mode()
        if not mode:
            return messagebox.showwarning('조회 항목 선택','수료조회 또는 예약조회를 한 개 이상 선택하세요.')
        self.run(mode,'all',date_filter=self.date_filter.get(),status_filter=statuses)

    def one_click_run(self):
        # 오늘까지 예약일이 도래한 모든 상태를 재검증한다. 기존 수료자와 보류·제외·오류도 포함한다.
        self.date_filter.set('due'); self._set_statuses(self.status_vars.keys()); self.update_target_preview()
        mode=self._selected_query_mode() or 'all'
        self.run(mode,'all',date_filter='due',status_filter='all')

    def _load_ai_stats(self):
        path=ROOT/'ai_region_stats.json'
        try:
            return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        except Exception:
            return {}

    def show_ai_report(self):
        stats=self._load_ai_stats()
        lines=['[AI 조회 최적화 분석]','']
        for r in ('서울','경기','인천'):
            x=stats.get(r,{})
            lines.append(f"{r}: 평균 {float(x.get('avg_seconds',0) or 0):.1f}초 · 당해연도 수료 발견률 {float(x.get('current_year_success_rate',0) or 0)*100:.1f}% · 오류율 {float(x.get('error_rate',0) or 0)*100:.1f}%")
        if not stats:
            lines.append('조회 이력이 아직 부족합니다. 조회를 완료할수록 추천순서가 자동 개선됩니다.')
        lines += ['', '[자동 판단]', '• 빠르고 당해연도 수료 발견률이 높은 기관을 우선 추천', '• 체크한 기관이 1개면 해당 기관을 항상 첫 번째로 조회', '• 수료 확인 즉시 나머지 기관 생략', '• 오류 기관은 마지막에 오류목록으로 분리']
        win=tk.Toplevel(self); win.title('AI 조회 분석'); win.geometry('640x440')
        txt=tk.Text(win,font=('맑은 고딕',10),padx=16,pady=16,wrap='word'); txt.pack(fill='both',expand=True)
        txt.insert('1.0','\n'.join(lines)); txt.configure(state='disabled')

    def _log(self,s):self.log.insert('end',s+'\n');self.log.see('end')
    def stop(self):
        if not self.proc:
            return messagebox.showinfo('조회 중지','현재 진행 중인 조회가 없습니다.')
        if self.stop_requested:
            return
        self.stop_requested=True
        try:
            if self.control_file:
                self.control_file.write_text('STOP',encoding='utf-8')
            self._log('[중지 요청] 현재 조회 중인 기사님 처리가 끝나면 안전하게 중지하고 결과파일을 저장합니다.')
            self.header_status.set('조회 중지 처리 중입니다...')
            self.ptext.set('현재 대상 처리 후 안전하게 중지합니다.')
            self.stop_btn.configure(state='disabled')
        except Exception as e:
            messagebox.showerror('중지 요청 오류',str(e))

    def resume_run(self):
        if self.proc:
            return messagebox.showwarning('실행 중','현재 조회가 진행 중입니다.')
        p=self.output or self.file.get().strip()
        if not p or not Path(p).exists():
            return messagebox.showwarning('재개 불가','중지 결과파일을 찾을 수 없습니다.')
        self.file.set(p)
        self.run('completion','unqueried')

    def reset_run_state(self):
        if self.proc:
            return messagebox.showwarning('실행 중','먼저 조회 중지를 눌러 안전하게 종료하세요.')
        self.pb['value']=0
        self.ptext.set('대기 중')
        self.header_status.set('새 조회를 시작할 수 있습니다.')
        self.last_error=''
        self.stop_requested=False
        self.stop_btn.configure(state='normal')
        self.resume_btn.configure(state='disabled')
        self.log.delete('1.0','end')

    def _poll(self):
        try:
            while True:
                x=self.q.get_nowait()
                if isinstance(x,tuple):
                    code=x[1]
                    self.stop_btn.configure(state='normal')
                    if code==0:
                        self.pb['value']=100
                        self.last_elapsed=max(time.time()-(self.run_started_at or time.time()),0)
                        if self.output and Path(self.output).exists():
                            self.file.set(self.output); self.refresh_file(); self._load_changes_from_output()
                        if self.pending_followup:
                            follow=self.pending_followup
                            self.pending_followup=None
                            self.header_status.set('수료조회 완료 · 예약조회를 시작합니다.')
                            self._log('[분리실행] 수료조회가 끝났습니다. 결과파일을 기준으로 예약조회를 시작합니다.')
                            self.after(250,lambda f=follow:self.run(*f))
                            self.stop_requested=False
                            continue
                        self.header_status.set('조회가 완료되었습니다.')
                        self.show_finish_popup(True)
                    elif code==2:
                        self.header_status.set('조회가 안전하게 중지되었습니다.')
                        if self.output and Path(self.output).exists(): self.file.set(self.output); self.refresh_file()
                        self.resume_btn.configure(state='normal')
                        self.show_stop_popup()
                    else:
                        self.header_status.set('오류가 발생했습니다. 오류 진단을 확인하세요.')
                        self.show_finish_popup(False)
                    self.stop_requested=False
                    continue
                if x.startswith('PROGRESS|'):
                    _,n,t,name,state=x.split('|',4)
                    total=self.selected_run_total or int(t)
                    self.pb['value']=int(n)/max(total,1)*100
                    elapsed=max(time.time()-(self.run_started_at or time.time()),0); done=max(int(n)-1,0); eta=(elapsed/done*(total-done)) if done else 0
                    eta_text=f' · 예상 {int(eta//60)}분 {int(eta%60)}초' if eta else ''
                    self.ptext.set(f'{n}/{total}명 · {name} · {state}{eta_text}')
                elif x.startswith('ROUTE|'):
                    _,name,region,mode=x.split('|',3); self._log(f'[기관배정] {name} → {region} · {mode}')
                elif x.startswith('RESULT|'):
                    _,name,status,cat,rdate,site=x.split('|',5); self._log(f'[결과] {name} · {cat or status} · {rdate} · {site}')
                elif x.startswith('SUMMARY|'):
                    d=json.loads(x.split('|',1)[1]);
                    for k in self.vars:self.vars[k].set(str(d.get(k,0)))
                elif x.startswith('SELECTED|'):
                    _,n,target=x.split('|',2)
                    self.selected_run_total=int(n)
                    self._log(f'[선택조회] 조건={target}, 대상={n}명')
                elif x.startswith('OUTPUT|'):self.output=x.split('|',1)[1]
                elif x.startswith('CHANGE_LOG|'):
                    _,log_path,count=x.split('|',2)
                    self._log(f'[상태변경 로그] {count}명 · {log_path}')
                elif x.startswith('STOPPED|'):
                    _,done,total,msg=x.split('|',3); self._log(f'[중지 완료] {done}/{total}명 처리 후 안전하게 종료했습니다.'); self.ptext.set(f'{done}/{total}명 처리 후 중지')
                elif x.startswith('AI_METRIC|'):
                    _,region,seconds,status=x.split('|',3); self.region_metrics[region]=(seconds,status)
                elif x.startswith('ERROR|'):
                    self.error_count += 1; self.last_error=x.replace('|',' · ');self._log('[오류] '+self.last_error)
                else:self._log(x)
        except queue.Empty:pass
        self.after(100,self._poll)


    def show_stop_popup(self):
        win=tk.Toplevel(self); win.title('조회 중지 완료'); win.geometry('580x360'); win.resizable(False,False); win.transient(self); win.grab_set(); win.configure(bg=WHITE)
        head=tk.Frame(win,bg=NAVY,height=82); head.pack(fill='x'); head.pack_propagate(False)
        tk.Label(head,text='조회가 안전하게 중지되었습니다.',bg=NAVY,fg='white',font=('맑은 고딕',17,'bold')).pack(anchor='w',padx=22,pady=(18,3))
        tk.Label(head,text='현재까지 조회한 결과는 파일에 저장되었습니다.',bg=NAVY,fg='#cfe5f7',font=('맑은 고딕',9)).pack(anchor='w',padx=22)
        body=tk.Frame(win,bg=WHITE); body.pack(fill='both',expand=True,padx=22,pady=18)
        tk.Label(body,text='계속하려면 재개를 누르세요. 처음부터 새로 진행하려면 새 조회 준비를 누른 뒤 원하는 조회 버튼을 선택하세요.',bg=WHITE,fg=TEXT,font=('맑은 고딕',10),wraplength=520,justify='left').pack(anchor='w',pady=(0,15))
        grid=tk.Frame(body,bg=WHITE); grid.pack(fill='x')
        ttk.Button(grid,text='중지된 조회 재개',style='Primary.TButton',command=lambda:(win.destroy(),self.resume_run())).grid(row=0,column=0,sticky='ew',padx=4,pady=5)
        ttk.Button(grid,text='새 조회 준비',style='ZC.TButton',command=lambda:(win.destroy(),self.reset_run_state())).grid(row=0,column=1,sticky='ew',padx=4,pady=5)
        ttk.Button(grid,text='현재 결과 파일 열기',style='ZC.TButton',command=self.open_result).grid(row=1,column=0,sticky='ew',padx=4,pady=5)
        ttk.Button(grid,text='저장 폴더 열기',style='ZC.TButton',command=self.open_folder).grid(row=1,column=1,sticky='ew',padx=4,pady=5)
        ttk.Button(grid,text='닫기',style='ZC.TButton',command=win.destroy).grid(row=2,column=0,columnspan=2,sticky='ew',padx=4,pady=(10,5))
        grid.columnconfigure(0,weight=1);grid.columnconfigure(1,weight=1)

    def show_finish_popup(self, success=True):
        """v2 방식의 조회 종료 선택창.

        조회가 끝난 뒤 사용자가 결과파일, 요약, 저장폴더, 디버그폴더를
        즉시 선택할 수 있게 하고 단순 확인창으로 끝내지 않는다.
        """
        win=tk.Toplevel(self)
        win.title('조회 완료' if success else '조회 오류')
        win.geometry('620x500')
        win.resizable(False,False)
        win.transient(self)
        win.grab_set()
        win.configure(bg=WHITE)

        head=tk.Frame(win,bg=NAVY,height=78)
        head.pack(fill='x'); head.pack_propagate(False)
        tk.Label(head,text='조회가 완료되었습니다.' if success else '조회 중 오류가 발생했습니다.',
                 bg=NAVY,fg='white',font=('맑은 고딕',17,'bold')).pack(anchor='w',padx=22,pady=(17,2))
        tk.Label(head,text='아래에서 바로 확인할 항목을 선택하세요.',
                 bg=NAVY,fg='#cfe5f7',font=('맑은 고딕',9)).pack(anchor='w',padx=22)

        body=tk.Frame(win,bg=WHITE)
        body.pack(fill='both',expand=True,padx=22,pady=18)
        result_path=self.output or self.file.get().strip()
        if success:
            changed=len(self.last_changes)
            elapsed=f'{int(self.last_elapsed//60)}분 {int(self.last_elapsed%60)}초'
            msg=f'결과 저장 완료 · 소요시간 {elapsed} · 변경 {changed}명\n결과파일이 다음 조회 대상파일로 자동 설정되었습니다.'
        else:
            msg=self.last_error or '오류 진단 또는 debug 폴더를 확인해 주세요.'
        tk.Label(body,text=msg,bg=WHITE,fg=TEXT,font=('맑은 고딕',10),wraplength=500,justify='left').pack(anchor='w',pady=(0,15))

        grid=tk.Frame(body,bg=WHITE); grid.pack(fill='x')
        ttk.Button(grid,text='결과 파일 열기',style='Primary.TButton',command=lambda:(self.open_result(),win.destroy())).grid(row=0,column=0,sticky='ew',padx=4,pady=5)
        ttk.Button(grid,text='결과 요약 보기',style='ZC.TButton',command=lambda:self.show_result_summary(win)).grid(row=0,column=1,sticky='ew',padx=4,pady=5)
        ttk.Button(grid,text='저장 폴더 열기',style='ZC.TButton',command=lambda:(self.open_folder(),win.destroy())).grid(row=1,column=0,sticky='ew',padx=4,pady=5)
        ttk.Button(grid,text='debug 폴더 열기',style='ZC.TButton',command=lambda:(self.open_debug(),win.destroy())).grid(row=1,column=1,sticky='ew',padx=4,pady=5)
        ttk.Button(grid,text='오늘 변경내역 보기',style='ZC.TButton',command=self.show_changes).grid(row=2,column=0,columnspan=2,sticky='ew',padx=4,pady=5)
        ttk.Button(grid,text='닫기',style='ZC.TButton',command=win.destroy).grid(row=3,column=0,columnspan=2,sticky='ew',padx=4,pady=(10,5))
        grid.columnconfigure(0,weight=1); grid.columnconfigure(1,weight=1)
        win.protocol('WM_DELETE_WINDOW',win.destroy)
        win.update_idletasks()
        x=self.winfo_rootx()+(self.winfo_width()-win.winfo_width())//2
        y=self.winfo_rooty()+(self.winfo_height()-win.winfo_height())//2
        win.geometry(f'+{max(x,0)}+{max(y,0)}')

    def show_result_summary(self, parent=None):
        win=tk.Toplevel(parent or self)
        win.title('조회 결과 요약')
        win.geometry('500x520')
        win.transient(parent or self)
        frame=ttk.Frame(win,padding=16); frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='조회 결과 요약',font=('맑은 고딕',16,'bold')).pack(anchor='w',pady=(0,12))
        txt=tk.Text(frame,font=('맑은 고딕',10),wrap='word',relief='flat',bg='#f6f8fb',padx=12,pady=12)
        txt.pack(fill='both',expand=True)
        lines=[]
        for key in ('전체','교육수료','입교예정','미수료','보류','제외','예약확인필요','정보변경확인','결과없음','조회오류','입력정보부족','미조회'):
            lines.append(f'{key}: {self.vars[key].get()}명')
        lines += ['',f'소요시간: {int(self.last_elapsed//60)}분 {int(self.last_elapsed%60)}초',f'변경 인원: {len(self.last_changes)}명']
        if self.last_changes:
            lines += ['', '[오늘 변경]'] + self.last_changes[:50]
        if self.output:
            lines += ['',f'결과파일: {self.output}']
        if self.last_error:
            lines += ['',f'최근 오류: {self.last_error}']
        txt.insert('1.0','\n'.join(lines)); txt.configure(state='disabled')
        ttk.Button(frame,text='닫기',style='ZC.TButton',command=win.destroy).pack(fill='x',pady=(10,0))

    def _make_snapshot(self, df):
        snap={}
        try:
            from unified_checker import people_from_df, text, row_result_state, requested_training_date
            for p in people_from_df(df):
                row=df.loc[p.row]
                key,status,cat=row_result_state(row)
                ident=f"{p.name}|{p.resident}|{p.phone}"
                snap[ident]={
                    'name':p.name, 'status':status or key, 'category':cat,
                    'completion':text(row.get('수료일','')),
                    'training':requested_training_date(row,p),
                }
        except Exception:
            return {}
        return snap

    def _load_changes_from_output(self):
        self.last_changes=[]
        try:
            from unified_checker import read_input
            _,_,df=read_input(Path(self.output))
            after=self._make_snapshot(df)
            for ident,new in after.items():
                old=self.before_snapshot.get(ident)
                if not old:
                    continue
                diffs=[]
                if old.get('status')!=new.get('status'):
                    diffs.append(f"{old.get('status') or '-'} → {new.get('status') or '-'}")
                if old.get('completion')!=new.get('completion'):
                    diffs.append(f"수료일 {old.get('completion') or '-'} → {new.get('completion') or '-'}")
                if old.get('training')!=new.get('training'):
                    diffs.append(f"교육시청일 {old.get('training') or '-'} → {new.get('training') or '-'}")
                if diffs:
                    self.last_changes.append(f"{new.get('name','')} · " + ' · '.join(diffs))
        except Exception as e:
            self._log(f'[변경비교 오류] {e}')

    def show_changes(self):
        win=tk.Toplevel(self); win.title('오늘 변경내역'); win.geometry('700x520'); win.transient(self)
        frame=ttk.Frame(win,padding=16); frame.pack(fill='both',expand=True)
        ttk.Label(frame,text=f'오늘 변경 {len(self.last_changes)}명',font=('맑은 고딕',16,'bold')).pack(anchor='w',pady=(0,10))
        txt=tk.Text(frame,font=('맑은 고딕',10),wrap='word',relief='flat',bg='#f6f8fb',padx=12,pady=12)
        txt.pack(fill='both',expand=True)
        txt.insert('1.0','\n'.join(self.last_changes) if self.last_changes else '이번 조회에서 변경된 기사 정보가 없습니다.')
        txt.configure(state='disabled')
        ttk.Button(frame,text='닫기',style='ZC.TButton',command=win.destroy).pack(fill='x',pady=(10,0))

    def open_result(self):
        p=self.output or self.file.get().strip()
        if p and Path(p).exists():os.startfile(p)
        else:messagebox.showwarning('결과 없음','먼저 파일을 선택하거나 조회를 실행하세요.')
    def open_folder(self):
        p=RESULTS_DIR
        p.mkdir(parents=True,exist_ok=True); os.startfile(str(p))
    def open_debug(self):
        p=DEBUG_DIR
        p.mkdir(parents=True,exist_ok=True); os.startfile(str(p))
    def show_error(self):messagebox.showinfo('최근 오류 진단',self.last_error or '현재 기록된 오류가 없습니다.')
    def apply_status_filter(self,key):self.current_filter=key;self.filter_label.set(f'{key} 명단');self.render_rows()
    def render_rows(self):
        if not hasattr(self,'tree'): return
        self.tree.delete(*self.tree.get_children()); q=self.search_var.get().strip().lower() if hasattr(self,'search_var') else ''
        for row in self.rows:
            name,status,completion_date,cat,rdate,site,note=row
            if status=='제외':
                key='제외'
            elif cat=='보류':
                key='보류'
            elif status=='교육수료':
                key='교육수료'
            elif cat=='입교예정':
                key='입교예정'
            elif status=='미수료':
                key='미수료'
            else:
                key='미조회'
            ok=self.current_filter=='전체' or key==self.current_filter
            if ok and (not q or q in ' '.join(row).lower()): self.tree.insert('','end',values=row)
    def make_pdf(self):
        p=self.output or self.file.get().strip()
        if not p or not Path(p).exists(): return messagebox.showwarning('결과 없음','먼저 조회를 실행하세요.')
        try:
            from report_generator import make_report
            out=make_report(p); messagebox.showinfo('PDF 생성 완료',f'PDF 보고서를 생성했습니다.\n{out}'); os.startfile(str(out))
        except Exception as e: messagebox.showerror('PDF 오류',str(e))
    def show_history(self):
        try:
            from history_store import connect, DB_PATH, db_size_text, delete_history_ids, delete_older_than, delete_all_history, compact
            with connect() as con:
                rows=con.execute('SELECT id,checked_at,company,name,site,reservation_date,method,completion_status,completion_date,category,course FROM education_history ORDER BY id DESC LIMIT 3000').fetchall()
            win=tk.Toplevel(self); win.title('교육이력 · 저장공간 관리'); win.geometry('1180x680')
            top=ttk.Frame(win,padding=10); top.pack(fill='x')
            sizevar=tk.StringVar(value=f'저장 위치: {DB_PATH}   |   현재 용량: {db_size_text()}   |   최근 3,000건 표시')
            ttk.Label(top,textvariable=sizevar).pack(side='left')
            cols=('ID','조회일시','회사','이름','사이트','예약일','방식','수료여부','수료일','구분','교육종류')
            t=ttk.Treeview(win,columns=cols,show='headings',selectmode='extended')
            widths={'ID':55,'조회일시':145,'회사':110,'이름':85,'사이트':70,'예약일':100,'방식':75,'수료여부':85,'수료일':105,'구분':95,'교육종류':130}
            for c in cols:t.heading(c,text=c);t.column(c,width=widths[c],anchor='center')
            for r in rows:t.insert('','end',values=r)
            t.pack(fill='both',expand=True,padx=10)
            btn=ttk.Frame(win,padding=10);btn.pack(fill='x')
            def reload_rows():
                t.delete(*t.get_children())
                with connect() as con: rr=con.execute('SELECT id,checked_at,company,name,site,reservation_date,method,completion_status,completion_date,category,course FROM education_history ORDER BY id DESC LIMIT 3000').fetchall()
                for x in rr:t.insert('','end',values=x)
                sizevar.set(f'저장 위치: {DB_PATH}   |   현재 용량: {db_size_text()}   |   최근 3,000건 표시')
            def del_selected():
                ids=[t.item(i,'values')[0] for i in t.selection()]
                if not ids:return messagebox.showwarning('선택 필요','삭제할 이력을 선택하세요.',parent=win)
                if messagebox.askyesno('선택 삭제',f'{len(ids)}건을 삭제할까요?',parent=win):delete_history_ids(ids);compact();reload_rows()
            def del_old():
                if messagebox.askyesno('오래된 이력 정리','2년이 지난 조회이력을 삭제할까요?\n현재 상태판정용 최신정보는 유지됩니다.',parent=win):delete_older_than(730);compact();reload_rows()
            def del_all():
                if messagebox.askyesno('전체 초기화','모든 조회이력과 변경감지 기준을 삭제할까요?\n다음 파일은 신규 대상으로 다시 판단됩니다.',parent=win):delete_all_history();compact();reload_rows()
            ttk.Button(btn,text='선택 이력 삭제',command=del_selected,style='ZC.TButton').pack(side='left',padx=3)
            ttk.Button(btn,text='2년 지난 이력 정리',command=del_old,style='ZC.TButton').pack(side='left',padx=3)
            ttk.Button(btn,text='DB 용량 최적화',command=lambda:(compact(),reload_rows()),style='ZC.TButton').pack(side='left',padx=3)
            ttk.Button(btn,text='전체 이력 초기화',command=del_all,style='Danger.TButton').pack(side='right',padx=3)
        except Exception as e: messagebox.showerror('이력 오류',str(e))

    def show_stats(self):
        p=self.output or self.file.get().strip()
        if not p or not Path(p).exists(): return messagebox.showwarning('결과 없음','먼저 파일을 선택하세요.')
        try:
            from unified_checker import read_input
            _,_,df=read_input(Path(p)); win=tk.Toplevel(self); win.title('교육 통계'); win.geometry('760x620'); txt=tk.Text(win,font=('맑은 고딕',11),padx=16,pady=16); txt.pack(fill='both',expand=True)
            counts,_=self._classify_df(df); lines=['[상태별 통계]']+[f'{k}: {v}명' for k,v in counts.items()]
            for col,title in [('사이트','사이트별 통계'),('교육방식','교육방식별 통계'),('소속(회사명)','회사별 통계')]:
                if col in df: lines+=['',f'[{title}]']+[f'{k}: {v}명' for k,v in df[col].fillna('공란').value_counts().items()]
            txt.insert('1.0','\n'.join(lines)); txt.configure(state='disabled')
        except Exception as e: messagebox.showerror('통계 오류',str(e))

if __name__=='__main__':App().mainloop()
