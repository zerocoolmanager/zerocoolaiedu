from __future__ import annotations
import json, os, queue, subprocess, sys, threading, time
from datetime import datetime, date
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3
import pandas as pd

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
RESULTS_DIR = ROOT / 'results'
DEBUG_DIR = ROOT / 'debug'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
DEBUG_DIR.mkdir(parents=True, exist_ok=True)
# Windows 11 / Fluent-inspired visual tokens.  Business logic intentionally stays below.
FONT='Segoe UI'; FONT_KR='맑은 고딕'
BG='#f3f3f3'; SURFACE='#ffffff'; SURFACE_ALT='#f9f9f9'; WHITE=SURFACE
TEXT='#1a1a1a'; TEXT_MUTED='#616161'; BORDER='#e5e5e5'; BORDER_STRONG='#d1d1d1'
BLUE='#0067c0'; BLUE_HOVER='#005a9e'; BLUE_PRESSED='#004578'; PALE='#eff6fc'
NAVY='#202020'; SUCCESS='#0f7b0f'; WARNING='#9d5d00'; DANGER='#c42b1c'
RADIUS=8

class RoundedButton(tk.Canvas):
    def __init__(self, master, text, command=None, bg=BLUE, fg='white', hover=None,
                 radius=RADIUS, height=42, font=(FONT_KR, 10, 'bold'), icon='', state='normal', **kwargs):
        # ttk 위젯(Frame 등)은 -bg 옵션을 지원하지 않을 수 있으므로 안전하게 배경색을 결정한다.
        try:
            parent_bg = master.cget('background')
        except Exception:
            try:
                parent_bg = master.winfo_toplevel().cget('background')
            except Exception:
                parent_bg = BG
        super().__init__(master, height=height, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor='hand2', **kwargs)
        self._text=text; self._icon=icon; self._command=command; self._bg=bg; self._fg=fg
        self._hover=hover or BLUE_HOVER; self._radius=radius; self._font=font; self._state=state
        self._pressed=False
        self.bind('<Configure>', lambda e:self._draw())
        self.bind('<Enter>', lambda e:self._paint(self._hover) if self._state!='disabled' else None)
        self.bind('<Leave>', lambda e:self._paint(self._bg) if self._state!='disabled' else None)
        self.bind('<ButtonPress-1>', self._press)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<space>', lambda e:self._click())
        self.bind('<Return>', lambda e:self._click())
        self._draw()
    def _round_rect(self,x1,y1,x2,y2,r,fill):
        pts=[x1+r,y1,x2-r,y1,x2,y1,x2,y1+r,x2,y2-r,x2,y2,x2-r,y2,x1+r,y2,x1,y2,x1,y2-r,x1,y1+r,x1,y1]
        return self.create_polygon(pts,smooth=True,splinesteps=24,fill=fill,outline='')
    def _draw(self):
        self.delete('all'); w=max(self.winfo_width(),80); h=max(self.winfo_height(),30)
        color='#e0e0e0' if self._state=='disabled' else self._bg
        self._round_rect(1,1,w-1,h-1,min(self._radius,h//2-2),color)
        label=(self._icon+'  ' if self._icon else '')+self._text
        self.create_text(w/2,h/2,text=label,fill='#9b9b9b' if self._state=='disabled' else self._fg,font=self._font)
    def _paint(self,color):
        if self._state!='disabled': self.itemconfigure(1,fill=color)
    def _click(self):
        if self._state!='disabled' and self._command: self._command()
    def _press(self, _event):
        if self._state!='disabled':
            self._pressed=True; self._paint(BLUE_PRESSED if self._bg==BLUE else self._hover)
    def _release(self, event):
        if self._state!='disabled' and self._pressed:
            self._pressed=False; self._paint(self._hover)
            if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
                self._click()
    def configure(self, cnf=None, **kw):
        if 'state' in kw: self._state=kw.pop('state')
        if 'text' in kw: self._text=kw.pop('text')
        super().configure(cnf or {}, **kw); self._draw()
    config=configure

class StatusCard(tk.Canvas):
    def __init__(self, master, title, variable, accent, command=None, icon='●'):
        super().__init__(master,height=82,bg=BG,highlightthickness=0,bd=0,cursor='hand2')
        self.title=title; self.variable=variable; self.accent=accent; self.command=command; self.icon=icon
        self.hovered=False
        self.bind('<Configure>',lambda e:self.draw())
        self.bind('<Button-1>',lambda e:self.command() if self.command else None)
        self.bind('<Enter>',lambda e:(setattr(self,'hovered',True),self.draw()))
        self.bind('<Leave>',lambda e:(setattr(self,'hovered',False),self.draw()))
        variable.trace_add('write',lambda *a:self.draw())
        self.draw()
    def draw(self):
        self.delete('all'); w=max(self.winfo_width(),80); h=max(self.winfo_height(),60)
        fill='#f7fbff' if self.hovered else SURFACE
        border='#b8d8f0' if self.hovered else BORDER
        self.create_rectangle(5,5,w-3,h-3,fill='#dedede',outline='')
        pts=[13,2,w-13,2,w-2,13,w-2,h-13,w-13,h-2,13,h-2,2,h-13,2,13]
        self.create_polygon(pts,smooth=True,splinesteps=18,fill=fill,outline=border)
        self.create_rectangle(2,14,5,h-14,fill=self.accent,outline='')
        self.create_oval(14,14,30,30,fill=self.accent,outline='')
        self.create_text(22,22,text=self.icon,fill='white',font=(FONT_KR,7,'bold'))
        self.create_text(38,21,text=self.title,anchor='w',fill=TEXT_MUTED,font=(FONT_KR,8))
        self.create_text(14,56,text=self.variable.get(),anchor='w',fill=TEXT,font=(FONT,19,'bold'))



class SelectableButton(tk.Button):
    def __init__(self, master, text, variable, command=None, icon='', selected_bg='#e8f1ff', selected_fg=BLUE, selected_border=BLUE,
                 normal_bg='#f5f5f5', normal_fg=TEXT_MUTED, normal_border=BORDER, **kwargs):
        self.variable=variable; self.user_command=command; self.icon=icon; self.base_text=text
        self.selected_bg=selected_bg; self.selected_fg=selected_fg; self.selected_border=selected_border
        self.normal_bg=normal_bg; self.normal_fg=normal_fg; self.normal_border=normal_border
        super().__init__(master,text=text,command=self._toggle,font=(FONT_KR,9,'bold'),relief='flat',bd=0,
                         padx=10,pady=8,cursor='hand2',anchor='center',takefocus=True,**kwargs)
        self.variable.trace_add('write',lambda *a:self._sync())
        self._sync()
    def _toggle(self):
        self.variable.set(not self.variable.get())
        if self.user_command: self.user_command()
    def _sync(self):
        selected=bool(self.variable.get())
        label=(f'{self.icon}  ' if self.icon else '')+self.base_text+('  ✓' if selected else '')
        self.configure(text=label,
                       bg=self.selected_bg if selected else self.normal_bg,
                       fg=self.selected_fg if selected else self.normal_fg,
                       activebackground=self.selected_bg if selected else '#ebebeb',
                       activeforeground=self.selected_fg if selected else self.normal_fg,
                       highlightbackground=self.selected_border if selected else self.normal_border,
                       highlightcolor=self.selected_border if selected else self.normal_border,
                       highlightthickness=1)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('ZeroCool AI · 서울·경기·인천 보수교육 관리 v15.0.3')
        self.geometry('1280x820'); self.minsize(1080,720)
        self.configure(bg=BG)
        self.q=queue.Queue(); self.proc=None; self.output=''; self.pending_followup=None; self.vars={}; self.date_filter=tk.StringVar(value='due'); self.status_vars={k:tk.BooleanVar(value=True) for k in ('completed','incomplete','scheduled','hold','excluded','error')}; self.status_all=tk.BooleanVar(value=True); self.last_error=''; self.rows=[]; self.current_filter='전체'; self.control_file=None; self.stop_requested=False; self.last_run=None; self.run_started_at=None; self.error_count=0; self.region_metrics={}; self.before_snapshot={}; self.last_changes=[]; self.last_elapsed=0; self.selected_run_total=0; self.query_vars={'completion':tk.BooleanVar(value=True),'reservation':tk.BooleanVar(value=True)}; self.query_all=tk.BooleanVar(value=True)
        self._styles(); self._ui(); self.after(0,self._apply_windows_chrome); self.after(100,self._poll)

    def _apply_windows_chrome(self):
        """Use the native Windows 11 light title bar when DWM is available."""
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            self.update_idletasks()
            hwnd=ctypes.windll.user32.GetParent(self.winfo_id())
            light=ctypes.c_int(0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,20,ctypes.byref(light),ctypes.sizeof(light))
            corner=ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd,33,ctypes.byref(corner),ctypes.sizeof(corner))
        except Exception:
            pass

    def _styles(self):
        s=ttk.Style(self); s.theme_use('clam')
        s.configure('.',font=(FONT_KR,9),background=BG,foreground=TEXT)
        s.configure('Main.TFrame',background=BG); s.configure('White.TFrame',background=SURFACE)
        s.configure('Panel.TLabelframe',background=SURFACE,bordercolor=BORDER,relief='solid',borderwidth=1)
        s.configure('Panel.TLabelframe.Label',background=SURFACE,foreground=TEXT,font=(FONT_KR,10,'bold'),padding=(4,0))
        s.configure('ZC.TButton',font=(FONT_KR,9,'bold'),padding=(14,9),background='#f5f5f5',foreground=TEXT,bordercolor=BORDER_STRONG,borderwidth=1,relief='solid')
        s.map('ZC.TButton',background=[('pressed','#e5e5e5'),('active','#ebebeb')],bordercolor=[('focus',BLUE)])
        s.configure('Primary.TButton',font=(FONT_KR,9,'bold'),padding=(14,9),background=BLUE,foreground='white',bordercolor=BLUE,borderwidth=1,relief='solid')
        s.map('Primary.TButton',background=[('pressed',BLUE_PRESSED),('active',BLUE_HOVER)],bordercolor=[('focus','#60a9dc')])
        s.configure('Filter.TRadiobutton',background=SURFACE,foreground=TEXT,font=(FONT_KR,9),padding=(10,7),indicatorcolor=SURFACE)
        s.map('Filter.TRadiobutton',background=[('active',SURFACE_ALT)],foreground=[('selected',BLUE)],indicatorcolor=[('selected',BLUE)])
        s.configure('TCheckbutton',background=SURFACE,foreground=TEXT,font=(FONT_KR,9),padding=(4,2),indicatorcolor=SURFACE)
        s.map('TCheckbutton',background=[('active',SURFACE)],indicatorcolor=[('selected',BLUE)])
        s.configure('Danger.TButton',font=(FONT_KR,9,'bold'),padding=(14,9),background=DANGER,foreground='white',bordercolor=DANGER)
        s.configure('Horizontal.TProgressbar',troughcolor='#e5e5e5',background=BLUE,bordercolor='#e5e5e5',lightcolor=BLUE,darkcolor=BLUE,thickness=6)
        s.configure('TNotebook',background=SURFACE,borderwidth=0,tabmargins=(0,0,0,0))
        s.configure('TNotebook.Tab',font=(FONT_KR,9),padding=(18,10),background=SURFACE,foreground=TEXT_MUTED,borderwidth=0)
        s.map('TNotebook.Tab',background=[('selected',PALE),('active',SURFACE_ALT)],foreground=[('selected',BLUE)])
        s.configure('TEntry',fieldbackground=SURFACE,foreground=TEXT,bordercolor=BORDER_STRONG,lightcolor=BORDER_STRONG,darkcolor=BORDER_STRONG,padding=(10,8))
        s.map('TEntry',bordercolor=[('focus',BLUE)],lightcolor=[('focus',BLUE)],darkcolor=[('focus',BLUE)])
        s.configure('Treeview',font=(FONT_KR,9),rowheight=34,background=SURFACE,fieldbackground=SURFACE,foreground=TEXT,bordercolor=BORDER)
        s.map('Treeview',background=[('selected','#cce8ff')],foreground=[('selected',TEXT)])
        s.configure('Treeview.Heading',font=(FONT_KR,9,'bold'),padding=(8,9),background='#f5f5f5',foreground=TEXT,bordercolor=BORDER,relief='flat')
        s.configure('Vertical.TScrollbar',background='#d6d6d6',troughcolor=SURFACE,bordercolor=SURFACE,arrowcolor=TEXT_MUTED)

    def _ui(self):
        header=tk.Frame(self,bg=SURFACE,height=92,highlightbackground=BORDER,highlightthickness=0); header.pack(fill='x'); header.pack_propagate(False)
        brand=tk.Frame(header,bg=BLUE,width=5); brand.pack(side='left',fill='y')
        title_group=tk.Frame(header,bg=SURFACE); title_group.pack(side='left',fill='y',padx=(24,0))
        tk.Label(title_group,text='ZEROCOOL  /  EDUCATION OPERATIONS',bg=SURFACE,fg=BLUE,font=(FONT,9,'bold')).pack(anchor='w',pady=(17,1))
        tk.Label(title_group,text='보수교육 관리 센터',bg=SURFACE,fg=TEXT,font=(FONT_KR,21,'bold')).pack(anchor='w')
        self.header_status=tk.StringVar(value='조회 파일을 선택해 주세요.')
        status_group=tk.Frame(header,bg=SURFACE); status_group.pack(side='right',fill='y',padx=24)
        tk.Label(status_group,text='SYSTEM STATUS',bg=SURFACE,fg=TEXT_MUTED,font=(FONT,8,'bold')).pack(anchor='e',pady=(22,2))
        tk.Label(status_group,textvariable=self.header_status,bg=SURFACE,fg=TEXT,font=(FONT_KR,9)).pack(anchor='e')
        tk.Frame(self,bg=BORDER,height=1).pack(fill='x')

        wrap=ttk.Frame(self,style='Main.TFrame',padding=(18,14,18,18)); wrap.pack(fill='both',expand=True)
        filebox=ttk.LabelFrame(wrap,text='데이터 소스 및 조회 기관',style='Panel.TLabelframe',padding=(16,13)); filebox.pack(fill='x')
        self.file=tk.StringVar(); ttk.Entry(filebox,textvariable=self.file,font=(FONT_KR,10)).grid(row=0,column=0,sticky='ew',padx=(0,10))
        ttk.Button(filebox,text='파일 선택',style='Primary.TButton',command=self.pick).grid(row=0,column=1,padx=4)
        ttk.Button(filebox,text='현황 새로고침',style='ZC.TButton',command=self.refresh_file).grid(row=0,column=2,padx=4)
        filebox.columnconfigure(0,weight=1)
        opt=ttk.Frame(filebox,style='White.TFrame'); opt.grid(row=1,column=0,columnspan=3,sticky='ew',pady=(9,0))
        self.seoul=tk.BooleanVar(value=True); self.gg=tk.BooleanVar(value=True); self.incheon=tk.BooleanVar(value=True)
        self.background_mode=tk.BooleanVar(value=True); self.ai_priority=tk.BooleanVar(value=False)
        ttk.Label(opt,text='조회 기관',background=SURFACE,foreground=TEXT_MUTED,font=(FONT_KR,8,'bold')).pack(side='left',padx=(0,10))
        ttk.Checkbutton(opt,text='서울',variable=self.seoul).pack(side='left',padx=(0,10))
        ttk.Checkbutton(opt,text='경기',variable=self.gg).pack(side='left',padx=(0,10))
        ttk.Checkbutton(opt,text='인천',variable=self.incheon).pack(side='left',padx=(0,18))
        ttk.Checkbutton(opt,text='백그라운드 모드(작은 창)',variable=self.background_mode).pack(side='left',padx=(4,12))
        ttk.Label(opt,text='조회창은 주 모니터 좌측 상단에 표시됩니다.',background=SURFACE,foreground=TEXT_MUTED).pack(side='right')

        self.alert_var=tk.StringVar(value='ⓘ 파일을 선택하면 확인이 필요한 항목을 자동으로 알려드립니다.')
        self.alert_bar=tk.Label(wrap,textvariable=self.alert_var,bg=PALE,fg=BLUE,font=(FONT_KR,9),anchor='w',padx=14,pady=9,
                                highlightbackground='#c7e0f4',highlightthickness=1)
        self.alert_bar.pack(fill='x',pady=(10,8))

        cards=ttk.Frame(wrap,style='Main.TFrame'); cards.pack(fill='x',pady=(0,10))
        specs=[('전체',BLUE,'Σ'),('교육수료','#107c10','✓'),('입교예정','#ca5010','◷'),('미수료','#5c2d91','!'),('보류','#8e562e','Ⅱ'),('제외','#605e5c','×'),('조회오류',DANGER,'!')]
        for i,(k,c,ico) in enumerate(specs):
            v=tk.StringVar(value='0'); self.vars[k]=v
            card=StatusCard(cards,k,v,c,command=lambda key=k:self.apply_status_filter(key),icon=ico)
            card.grid(row=0,column=i,sticky='nsew',padx=(0 if i==0 else 4,0),pady=1)
            cards.columnconfigure(i,weight=1,uniform='status')

        content=ttk.Panedwindow(wrap,orient='horizontal'); content.pack(fill='both',expand=True)
        left_panel=ttk.LabelFrame(content,text='조회 구성',style='Panel.TLabelframe',padding=8)
        right=ttk.LabelFrame(content,text='작업 모니터',style='Panel.TLabelframe',padding=16)
        content.add(left_panel,weight=2); content.add(right,weight=5)

        # 왼쪽 기능 버튼 영역은 창 높이가 작아도 사용할 수 있도록 세로 스크롤 적용
        left_canvas=tk.Canvas(left_panel,bg=WHITE,highlightthickness=0,width=315)
        left_scroll=ttk.Scrollbar(left_panel,orient='vertical',command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_scroll.pack(side='right',fill='y')
        left_canvas.pack(side='left',fill='both',expand=True)
        left=ttk.Frame(left_canvas,style='White.TFrame',padding=(5,3))
        left_window=left_canvas.create_window((0,0),window=left,anchor='nw')
        left.bind('<Configure>',lambda e:left_canvas.configure(scrollregion=left_canvas.bbox('all')))
        left_canvas.bind('<Configure>',lambda e:left_canvas.itemconfigure(left_window,width=e.width))
        def _left_wheel(e):
            left_canvas.yview_scroll(int(-1*(e.delta/120)), 'units')
        left_canvas.bind('<Enter>',lambda e:left_canvas.bind_all('<MouseWheel>',_left_wheel))
        left_canvas.bind('<Leave>',lambda e:left_canvas.unbind_all('<MouseWheel>'))

        # v11: 날짜는 단일 선택, 상태는 중복 선택으로 조합한다.
        r=0
        tk.Label(left,text='조회 조건',bg=SURFACE,fg=TEXT,font=(FONT_KR,13,'bold')).grid(row=r,column=0,columnspan=2,sticky='w',pady=(6,2)); r+=1
        tk.Label(left,text='대상과 조회 항목을 선택하세요.',bg=SURFACE,fg=TEXT_MUTED,font=(FONT_KR,8)).grid(row=r,column=0,columnspan=2,sticky='w',pady=(0,10)); r+=1

        date_box=tk.LabelFrame(left,text=' 1  날짜 범위 ',bg=SURFACE,fg=TEXT_MUTED,font=(FONT_KR,9,'bold'),bd=1,relief='solid',highlightthickness=0,highlightbackground=BORDER)
        date_box.grid(row=r,column=0,columnspan=2,sticky='ew',padx=3,pady=3); r+=1
        ttk.Radiobutton(date_box,text='전체 날짜',value='all',variable=self.date_filter,style='Filter.TRadiobutton',command=self.update_target_preview).pack(side='left',fill='x',expand=True,padx=4,pady=4)
        ttk.Radiobutton(date_box,text='오늘까지',value='due',variable=self.date_filter,style='Filter.TRadiobutton',command=self.update_target_preview).pack(side='left',fill='x',expand=True,padx=4,pady=4)

        status_box=tk.LabelFrame(left,text=' 2  상태 범위 · 복수 선택 가능 ',bg=SURFACE,fg=BLUE,font=(FONT_KR,9,'bold'),bd=1,relief='solid',highlightthickness=0,highlightbackground=BORDER)
        status_box.grid(row=r,column=0,columnspan=2,sticky='ew',padx=3,pady=(7,3)); r+=1
        status_head=tk.Frame(status_box,bg=WHITE)
        status_head.grid(row=0,column=0,columnspan=2,sticky='ew',padx=5,pady=(5,3))
        tk.Label(status_head,text='조회할 상태를 선택하세요',bg=SURFACE,fg=TEXT_MUTED,font=(FONT_KR,8)).pack(side='left')
        tk.Button(status_head,text='전체 선택',command=self.toggle_all_statuses_button,font=(FONT_KR,8,'bold'),
                  bg='#f5f5f5',fg=TEXT,activebackground='#ebebeb',activeforeground=BLUE,relief='flat',bd=0,padx=10,pady=5,cursor='hand2').pack(side='right')
        status_items=[('수료','completed','●','#18a66a'),('미수료','incomplete','×','#e84d5b'),('입교예정','scheduled','▣','#246fe5'),('보류','hold','◷','#e7a317'),('제외','excluded','−','#7657ef'),('조회오류','error','△','#7d8793')]
        for i,(label,value,icon,color) in enumerate(status_items):
            SelectableButton(status_box,text=label,variable=self.status_vars[value],icon=icon,command=self.on_status_changed,
                             selected_bg='#eef8f3' if value=='completed' else '#edf4ff',selected_fg=color,selected_border=color).grid(row=1+i//2,column=i%2,sticky='ew',padx=5,pady=4)
        status_box.columnconfigure(0,weight=1); status_box.columnconfigure(1,weight=1)

        query_box=tk.LabelFrame(left,text=' 3  조회 항목 · 복수 선택 가능 ',bg=SURFACE,fg=BLUE,font=(FONT_KR,9,'bold'),bd=1,relief='solid',highlightthickness=0,highlightbackground=BORDER)
        query_box.grid(row=r,column=0,columnspan=2,sticky='ew',padx=3,pady=(7,3)); r+=1
        query_head=tk.Frame(query_box,bg=WHITE); query_head.grid(row=0,column=0,columnspan=2,sticky='ew',padx=5,pady=(5,3))
        tk.Label(query_head,text='하나만 또는 둘 다 선택할 수 있습니다',bg=SURFACE,fg=TEXT_MUTED,font=(FONT_KR,8)).pack(side='left')
        tk.Button(query_head,text='전체 선택',command=self.toggle_all_queries_button,font=(FONT_KR,8,'bold'),
                  bg='#f5f5f5',fg=TEXT,activebackground='#ebebeb',activeforeground=BLUE,relief='flat',bd=0,padx=10,pady=5,cursor='hand2').pack(side='right')
        SelectableButton(query_box,text='수료조회',variable=self.query_vars['completion'],icon='🎓',command=self.on_query_changed,
                         selected_bg='#eef8f3',selected_fg='#15955f',selected_border='#18a66a').grid(row=1,column=0,sticky='ew',padx=5,pady=(4,6))
        SelectableButton(query_box,text='예약조회',variable=self.query_vars['reservation'],icon='▣',command=self.on_query_changed,
                         selected_bg='#edf4ff',selected_fg=BLUE,selected_border=BLUE).grid(row=1,column=1,sticky='ew',padx=5,pady=(4,6))
        query_box.columnconfigure(0,weight=1); query_box.columnconfigure(1,weight=1)
        self.query_note=tk.StringVar(value='둘 다 선택하면 수료조회 → 예약조회 순서로 자동 진행됩니다.')
        tk.Label(query_box,textvariable=self.query_note,bg='#f1faf1',fg=SUCCESS,font=(FONT_KR,8),anchor='w',padx=8,pady=7).grid(row=2,column=0,columnspan=2,sticky='ew',padx=5,pady=(0,6))

        # v13.1: 자주 쓰는 기능만 노출하고 나머지는 더보기로 이동
        self.target_preview=tk.StringVar(value='조회 조건을 계산합니다.')
        preview=tk.Label(left,textvariable=self.target_preview,bg=PALE,fg=TEXT,font=(FONT_KR,9,'bold'),justify='left',anchor='w',padx=12,pady=11,wraplength=280,
                         highlightbackground='#c7e0f4',highlightthickness=1)
        preview.grid(row=r,column=0,columnspan=2,sticky='ew',padx=3,pady=(8,7)); r+=1

        RoundedButton(left,text='선택 조건으로 조회',icon='▶',command=self.run_filtered,bg=BLUE,hover=BLUE_HOVER,height=46,radius=RADIUS).grid(row=r,column=0,columnspan=2,sticky='ew',padx=3,pady=6); r+=1

        quick=tk.Frame(left,bg=WHITE); quick.grid(row=r,column=0,columnspan=2,sticky='ew',padx=3,pady=(5,2)); r+=1
        RoundedButton(quick,text='오늘 업무',icon='☀',command=self.one_click_run,bg=SUCCESS,hover='#0b650b',height=40).pack(side='left',fill='x',expand=True,padx=(0,3))
        RoundedButton(quick,text='조회 결과 보기',icon='▤',command=self.open_result,bg='#5c2d91',hover='#4b2277',height=40).pack(side='left',fill='x',expand=True,padx=(3,0))

        RoundedButton(left,text='기타 기능',icon='⋯',command=self.show_more_actions,bg='#f0f0f0',fg=TEXT,hover='#e5e5e5',height=38).grid(row=r,column=0,columnspan=2,sticky='ew',padx=3,pady=(6,3)); r+=1
        self.update_note=tk.StringVar(value='v15.0.3 · 정상 화면 캡처 제거 · 오류 발생 시에만 HTML/PNG 저장')
        tk.Label(left,textvariable=self.update_note,bg=SURFACE,fg=TEXT_MUTED,font=(FONT_KR,8),wraplength=280,justify='left').grid(row=r,column=0,columnspan=2,sticky='ew',padx=3,pady=(6,8)); r+=1
        ttk.Separator(left).grid(row=r,column=0,columnspan=2,sticky='ew',pady=5);r+=1
        left.columnconfigure(0,weight=1); left.columnconfigure(1,weight=1)
        self.stop_btn=RoundedButton(left,text='조회 중지',icon='■',command=self.stop,bg=DANGER,hover='#a4261d',height=38); self.stop_btn.grid(row=r,column=0,columnspan=2,sticky='ew',padx=3,pady=(4,3))
        self.resume_btn=RoundedButton(left,text='중지된 조회 재개',icon='▶',command=self.resume_run,bg=BLUE,hover=BLUE_HOVER,height=38,state='disabled'); self.resume_btn.grid(row=r+1,column=0,sticky='ew',padx=3,pady=3)
        self.reset_btn=RoundedButton(left,text='새 조회 준비',icon='↺',command=self.reset_run_state,bg='#f0f0f0',fg=TEXT,hover='#e5e5e5',height=38); self.reset_btn.grid(row=r+1,column=1,sticky='ew',padx=3,pady=3)

        progress_header=ttk.Frame(right,style='White.TFrame'); progress_header.pack(fill='x',pady=(0,4))
        ttk.Label(progress_header,text='현재 작업',background=SURFACE,foreground=TEXT_MUTED,font=(FONT_KR,8,'bold')).pack(side='left')
        self.ptext=tk.StringVar(value='대기 중'); ttk.Label(progress_header,textvariable=self.ptext,background=SURFACE,foreground=TEXT,font=(FONT_KR,9,'bold')).pack(side='right')
        self.pb=ttk.Progressbar(right,maximum=100); self.pb.pack(fill='x',pady=(6,10))
        tabs=ttk.Notebook(right); tabs.pack(fill='both',expand=True)
        logf=ttk.Frame(tabs); resultf=ttk.Frame(tabs); tabs.add(logf,text='실시간 로그'); tabs.add(resultf,text='조회 결과')
        self.log=tk.Text(logf,font=('Cascadia Mono',9),bg='#1e1e1e',fg='#f5f5f5',insertbackground='white',selectbackground=BLUE,wrap='word',relief='flat',padx=14,pady=12); self.log.pack(fill='both',expand=True)
        filterbar=ttk.Frame(resultf,style='White.TFrame'); filterbar.pack(fill='x',pady=(8,8))
        ttk.Label(filterbar,text='검색',background=SURFACE,foreground=TEXT_MUTED,font=(FONT_KR,8,'bold')).pack(side='left',padx=(2,8))
        self.search_var=tk.StringVar(); ent=ttk.Entry(filterbar,textvariable=self.search_var,width=24); ent.pack(side='left'); ent.bind('<KeyRelease>',lambda e:self.render_rows())
        self.filter_label=tk.StringVar(value='전체 명단'); ttk.Label(filterbar,textvariable=self.filter_label).pack(side='right')
        cols=('이름','수료여부','수료일','구분','교육시청일(예정일)','사이트','비고'); self.tree=ttk.Treeview(resultf,columns=cols,show='headings')
        widths={'이름':95,'수료여부':85,'수료일':210,'구분':105,'교육시청일(예정일)':125,'사이트':75,'비고':140}
        for c in cols:self.tree.heading(c,text=c);self.tree.column(c,width=widths[c],anchor='center')
        self.tree.pack(fill='both',expand=True)

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
