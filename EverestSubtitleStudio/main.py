import sys, os, json, re, traceback
from pathlib import Path
from PySide6.QtCore import Qt, QRectF, Signal, QUrl, QThread, QObject
from PySide6.QtGui import QAction, QColor, QBrush, QPen, QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFileDialog, QMessageBox,
    QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton, QComboBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit, QProgressBar, QToolBar,
    QAbstractItemView, QFrame, QFormLayout, QGroupBox, QSlider, QStyle, QLineEdit)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

APP_NAME = "Everest Subtitle Studio"

DARK_QSS = """
QWidget { background:#171b22; color:#e8edf4; font-family:'Segoe UI'; font-size:10pt; }
QMainWindow { background:#171b22; }
QFrame, QGroupBox { border:1px solid #303946; border-radius:14px; }
QGroupBox { margin-top:12px; padding:12px; font-weight:600; }
QGroupBox::title { subcontrol-origin: margin; left:14px; padding:0 5px; }
QPushButton { background:#293442; border:1px solid #3a4859; border-radius:12px; padding:9px 15px; }
QPushButton:hover { background:#35465a; }
QPushButton:pressed { background:#223040; }
QPushButton#primary { background:#397eae; border:0; font-weight:600; }
QPushButton#primary:hover { background:#478fbe; }
QComboBox, QSpinBox, QLineEdit, QPlainTextEdit { background:#202833; border:1px solid #3a4859; border-radius:9px; padding:7px; }
QTableWidget { background:#202833; alternate-background-color:#252f3b; border:1px solid #303946; border-radius:12px; gridline-color:#303946; selection-background-color:#315d7c; }
QHeaderView::section { background:#293442; padding:8px; border:0; font-weight:600; }
QProgressBar { background:#202833; border:0; border-radius:6px; height:12px; text-align:center; }
QProgressBar::chunk { background:#48a18c; border-radius:6px; }
QSlider::groove:horizontal { height:6px; background:#394655; border-radius:3px; }
QSlider::handle:horizontal { background:#5aa4d2; width:14px; margin:-5px 0; border-radius:7px; }
"""


def srt_time(seconds):
    ms = max(0, int(round(seconds * 1000)))
    h, rem = divmod(ms, 3600000); m, rem = divmod(rem, 60000); s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def clean_punctuation(text):
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([,.!?;:])(?=[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű])", r"\1 ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text:
        text = text[0].upper() + text[1:]
    return text


def split_lines(text, max_chars=42):
    words = text.split()
    lines, line = [], ""
    for word in words:
        candidate = (line + " " + word).strip()
        if len(candidate) <= max_chars or not line:
            line = candidate
        else:
            lines.append(line); line = word
    if line: lines.append(line)
    return lines


def group_words(words, max_words=10, max_chars=42, max_lines=2):
    """Group word timestamp records without cutting punctuation/short clauses unnecessarily."""
    groups, current = [], []
    def fits(candidate):
        txt = " ".join(w["word"].strip() for w in candidate)
        return len(candidate) <= max_words and len(split_lines(txt, max_chars)) <= max_lines
    for word in words:
        token = word["word"].strip()
        if not token: continue
        candidate = current + [word]
        if current and not fits(candidate):
            groups.append(current); current = [word]
        else:
            current = candidate
        # Prefer sentence boundaries, but don't create tiny captions.
        if current and re.search(r"[.!?][\"'’”)]?$", current[-1]["word"].strip()) and len(current) >= 4:
            groups.append(current); current = []
    if current: groups.append(current)
    result = []
    for g in groups:
        txt = clean_punctuation(" ".join(x["word"].strip() for x in g))
        result.append({"start": float(g[0]["start"]), "end": float(g[-1]["end"]), "text": txt, "words": g})
    return result


class TranscribeWorker(QObject):
    progress = Signal(str)
    done = Signal(list)
    failed = Signal(str)
    def __init__(self, path, language, model_name, max_words, max_chars, max_lines):
        super().__init__(); self.path=path; self.language=language; self.model_name=model_name
        self.max_words=max_words; self.max_chars=max_chars; self.max_lines=max_lines
    def run(self):
        try:
            from faster_whisper import WhisperModel
            cache = Path.home() / ".everest_subtitle_studio" / "models"
            cache.mkdir(parents=True, exist_ok=True)
            self.progress.emit(f"Modell betöltése: {self.model_name}. Első alkalommal internetkapcsolat kell a letöltéshez.")
            model = WhisperModel(self.model_name, device="cpu", compute_type="int8", download_root=str(cache), cpu_threads=4)
            self.progress.emit("Beszédfelismerés folyamatban… Ez a gépeden hosszabb ideig tarthat.")
            lang = None if self.language == "Automatikus" else ("hu" if self.language == "Magyar" else "en")
            segments, info = model.transcribe(self.path, language=lang, beam_size=5, word_timestamps=True,
                                              vad_filter=True, condition_on_previous_text=True)
            all_words=[]
            for seg in segments:
                if seg.words:
                    for w in seg.words:
                        all_words.append({"start": w.start, "end": w.end, "word": w.word})
                else:
                    # Fallback for unusual segments without word alignment.
                    tokens = seg.text.split()
                    if tokens:
                        duration=max(0.01, seg.end-seg.start)
                        for i,t in enumerate(tokens):
                            all_words.append({"start":seg.start+duration*i/len(tokens),"end":seg.start+duration*(i+1)/len(tokens),"word":t})
            self.progress.emit(f"Felismerés kész. Nyelv: {info.language}. Feliratok tagolása…")
            self.done.emit(group_words(all_words, self.max_words, self.max_chars, self.max_lines))
        except Exception as e:
            self.failed.emit(f"{e}\n\n{traceback.format_exc()}")


class Timeline(QWidget):
    seekRequested = Signal(float)
    edgeChanged = Signal(int, float, float)
    splitRequested = Signal(int, float)
    def __init__(self):
        super().__init__(); self.setMinimumHeight(125); self.setMouseTracking(True)
        self.items=[]; self.duration=60.0; self.selected=-1; self.scale=1.0; self.drag=None; self.origin=0.0
    def set_data(self, items, duration=None):
        self.items=items
        if duration: self.duration=max(duration, 1)
        elif items: self.duration=max(max(x['end'] for x in items)+2, 10)
        self.update()
    def set_selected(self, i): self.selected=i; self.update()
    def x_at(self, t): return 12 + (t/self.duration)*(self.width()-24)
    def t_at(self, x): return max(0, min(self.duration, (x-12)/(self.width()-24)*self.duration))
    def paintEvent(self, ev):
        from PySide6.QtGui import QPainter
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor('#202833'))
        p.setPen(QPen(QColor('#465362'),1))
        for n in range(11):
            x=12+n*(self.width()-24)/10; p.drawLine(int(x),22,int(x),self.height()-18)
            p.setPen(QColor('#aab5c2')); p.drawText(int(x+3),15,f"{self.duration*n/10:.0f}s"); p.setPen(QPen(QColor('#465362'),1))
        y=43; h=48
        for i,it in enumerate(self.items):
            x1=self.x_at(it['start']); x2=max(x1+8,self.x_at(it['end']))
            color=QColor('#397eae' if i==self.selected else '#347d70')
            p.setBrush(QBrush(color)); p.setPen(QPen(QColor('#8ac6df') if i==self.selected else color,2))
            p.drawRoundedRect(QRectF(x1,y,x2-x1,h),8,8)
            p.setPen(QColor('#ffffff')); label=it['text'].replace('\n',' ')
            p.drawText(QRectF(x1+6,y+4,max(0,x2-x1-12),h-8),Qt.AlignVCenter|Qt.AlignLeft,label[:70])
        p.end()
    def mousePressEvent(self,e):
        if e.button()!=Qt.LeftButton: return
        x=e.position().x(); y=e.position().y()
        if y>=38 and y<=100:
            for i,it in enumerate(self.items):
                x1=self.x_at(it['start']); x2=self.x_at(it['end'])
                if x1-6<=x<=x1+7: self.drag=('left',i); return
                if x2-7<=x<=x2+7: self.drag=('right',i); return
                if x1<=x<=x2:
                    self.selected=i; self.drag=('move',i,x,self.items[i]['start'],self.items[i]['end']); self.update(); return
        self.seekRequested.emit(self.t_at(x))
    def mouseMoveEvent(self,e):
        if not self.drag: return
        x=e.position().x(); t=self.t_at(x); kind=self.drag[0]; i=self.drag[1]
        if kind=='left':
            it=self.items[i]; self.edgeChanged.emit(i,min(t,it['end']-0.08),it['end'])
        elif kind=='right':
            it=self.items[i]; self.edgeChanged.emit(i,it['start'],max(t,it['start']+0.08))
        elif kind=='move':
            _,i,x0,s0,e0=self.drag; delta=(x-x0)/(self.width()-24)*self.duration
            ns=max(0,s0+delta); self.edgeChanged.emit(i,ns,ns+(e0-s0))
    def mouseReleaseEvent(self,e): self.drag=None


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle(APP_NAME); self.resize(1450,900)
        self.media_path=None; self.items=[]; self.worker_thread=None; self.worker=None; self.current_project=None
        self.player=QMediaPlayer(self); self.audio=QAudioOutput(self); self.player.setAudioOutput(self.audio)
        self.build_ui(); self.player.positionChanged.connect(self.position_changed); self.player.durationChanged.connect(self.duration_changed)
    def build_ui(self):
        toolbar=QToolBar(); toolbar.setMovable(False); self.addToolBar(toolbar)
        for label,fn in [("Média megnyitása",self.open_file),("Projekt megnyitása",self.open_project),("Projekt mentése",self.save_project),("SRT export",self.export_srt)]:
            a=QAction(label,self); a.triggered.connect(fn); toolbar.addAction(a)
        root=QWidget(); lay=QVBoxLayout(root); lay.setContentsMargins(16,12,16,14); lay.setSpacing(12)
        header=QHBoxLayout(); title=QLabel("Everest Subtitle Studio"); title.setStyleSheet("font-size:22pt;font-weight:700;border:0;")
        self.status=QLabel("Készen áll"); self.status.setStyleSheet("color:#9fb1c3;border:0;")
        header.addWidget(title); header.addStretch(); header.addWidget(self.status); lay.addLayout(header)
        settings=QGroupBox("Automatikus feliratozás beállításai"); form=QHBoxLayout(settings)
        self.lang=QComboBox(); self.lang.addItems(["Automatikus","Magyar","Angol"])
        self.model=QComboBox(); self.model.addItems(["large-v3","medium","small"])
        self.max_words=QSpinBox(); self.max_words.setRange(4,25); self.max_words.setValue(10)
        self.max_chars=QSpinBox(); self.max_chars.setRange(20,60); self.max_chars.setValue(42)
        self.max_lines=QSpinBox(); self.max_lines.setRange(1,2); self.max_lines.setValue(2)
        for lab,w in [("Nyelv",self.lang),("Modell",self.model),("Max. szó",self.max_words),("Karakter/sor",self.max_chars),("Max. sor",self.max_lines)]:
            form.addWidget(QLabel(lab)); form.addWidget(w)
        self.transcribe_btn=QPushButton("Felirat készítése"); self.transcribe_btn.setObjectName('primary'); self.transcribe_btn.clicked.connect(self.transcribe); form.addWidget(self.transcribe_btn)
        lay.addWidget(settings)
        split=QSplitter(Qt.Vertical)
        upper=QSplitter(Qt.Horizontal)
        video_panel=QFrame(); vp=QVBoxLayout(video_panel); vp.addWidget(QLabel("Videóelőnézet"))
        self.video=QVideoWidget(); self.video.setMinimumHeight(230); self.video.setStyleSheet("background:#080b10;border:0;border-radius:12px;")
        self.player.setVideoOutput(self.video); vp.addWidget(self.video,1)
        controls=QHBoxLayout(); self.play_btn=QPushButton("Lejátszás / Szünet"); self.play_btn.clicked.connect(self.toggle_play)
        self.position=QLabel("00:00.000"); controls.addWidget(self.play_btn); controls.addWidget(self.position); controls.addStretch(); vp.addLayout(controls)
        editor=QFrame(); ep=QVBoxLayout(editor); ep.addWidget(QLabel("Kiválasztott felirat szövege"))
        self.text_edit=QPlainTextEdit(); self.text_edit.setPlaceholderText("Válassz ki egy feliratot a listából…"); self.text_edit.textChanged.connect(self.text_edited); ep.addWidget(self.text_edit,1)
        timing=QHBoxLayout(); self.start_edit=QLineEdit(); self.end_edit=QLineEdit(); self.start_edit.setPlaceholderText("Kezdés mp"); self.end_edit.setPlaceholderText("Vége mp")
        timing.addWidget(QLabel("Kezdés")); timing.addWidget(self.start_edit); timing.addWidget(QLabel("Vége")); timing.addWidget(self.end_edit); ep.addLayout(timing)
        editbtn=QHBoxLayout()
        for txt,fn in [("Választott szó előtti vágás",self.split_before_word),("Kurzor szerinti vágás",self.split_cursor),("Összevonás",self.merge),("Módosítás mentése",self.apply_edit)]:
            b=QPushButton(txt); b.clicked.connect(fn); editbtn.addWidget(b)
        ep.addLayout(editbtn); upper.addWidget(video_panel); upper.addWidget(editor); upper.setSizes([650,650]); split.addWidget(upper)
        bottom=QFrame(); bp=QVBoxLayout(bottom); bp.addWidget(QLabel("Feliratlista – kattints egy sorra a szerkesztéshez"))
        self.table=QTableWidget(0,4); self.table.setHorizontalHeaderLabels(["#","Kezdés","Befejezés","Feliratszöveg"])
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents); self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents); self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents); self.table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setAlternatingRowColors(True); self.table.itemSelectionChanged.connect(self.select_row); bp.addWidget(self.table,1)
        self.timeline=Timeline(); self.timeline.seekRequested.connect(self.seek_seconds); self.timeline.edgeChanged.connect(self.edge_changed); bp.addWidget(QLabel("Idővonal – a blokkok széleit húzva módosítható az időzítés")); bp.addWidget(self.timeline)
        split.addWidget(bottom); split.setSizes([430,400]); lay.addWidget(split,1)
        self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); lay.addWidget(self.progress)
        self.setCentralWidget(root)
    def msg(self,title,body): QMessageBox.information(self,title,body)
    def open_file(self):
        path,_=QFileDialog.getOpenFileName(self,"Hang- vagy videófájl megnyitása","","Médiafájlok (*.mp3 *.mp4 *.wav *.m4a *.mkv *.mov *.flac *.aac *.ogg);;Minden fájl (*)")
        if path:
            self.media_path=path; self.player.setSource(QUrl.fromLocalFile(path)); self.status.setText(Path(path).name)
    def transcribe(self):
        if not self.media_path: self.msg("Hiányzó fájl","Először nyiss meg egy hang- vagy videófájlt."); return
        self.transcribe_btn.setEnabled(False); self.progress.show(); self.status.setText("Feldolgozás…")
        self.worker_thread=QThread(); self.worker=TranscribeWorker(self.media_path,self.lang.currentText(),self.model.currentText(),self.max_words.value(),self.max_chars.value(),self.max_lines.value())
        self.worker.moveToThread(self.worker_thread); self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.status.setText); self.worker.done.connect(self.transcription_done); self.worker.failed.connect(self.transcription_failed)
        self.worker.done.connect(self.worker_thread.quit); self.worker.failed.connect(self.worker_thread.quit); self.worker_thread.start()
    def transcription_done(self, items):
        self.items=items; self.refresh_table(); self.timeline.set_data(self.items); self.progress.hide(); self.transcribe_btn.setEnabled(True); self.status.setText(f"Elkészült: {len(items)} felirat")
    def transcription_failed(self, error):
        self.progress.hide(); self.transcribe_btn.setEnabled(True); self.status.setText("Hiba történt")
        QMessageBox.critical(self,"Feldolgozási hiba",error[:5000])
    def refresh_table(self, select=-1):
        self.table.blockSignals(True); self.table.setRowCount(len(self.items))
        for i,it in enumerate(self.items):
            vals=[str(i+1),f"{it['start']:.3f}",f"{it['end']:.3f}",it['text']]
            for c,v in enumerate(vals):
                item=QTableWidgetItem(v); item.setFlags(item.flags() & ~Qt.ItemIsEditable if c<3 else item.flags()); self.table.setItem(i,c,item)
        self.table.blockSignals(False)
        if select>=0 and select<len(self.items): self.table.selectRow(select)
        self.timeline.set_data(self.items,self.player.duration()/1000 if self.player.duration() else None)
    def select_row(self):
        rows=self.table.selectionModel().selectedRows()
        if not rows:return
        i=rows[0].row(); self.timeline.set_selected(i); it=self.items[i]
        self.text_edit.blockSignals(True); self.text_edit.setPlainText(it['text']); self.text_edit.blockSignals(False)
        self.start_edit.setText(f"{it['start']:.3f}"); self.end_edit.setText(f"{it['end']:.3f}"); self.seek_seconds(it['start'])
    def selected_index(self):
        rows=self.table.selectionModel().selectedRows(); return rows[0].row() if rows else -1
    def text_edited(self): pass
    def apply_edit(self):
        i=self.selected_index()
        if i<0:return
        try: s=float(self.start_edit.text().replace(',','.')); e=float(self.end_edit.text().replace(',','.'))
        except ValueError: self.msg("Hibás idő","Az időpontokat másodpercben add meg."); return
        if e<=s: self.msg("Hibás idő","A befejezésnek a kezdés után kell lennie."); return
        self.items[i]['start']=s; self.items[i]['end']=e; self.items[i]['text']=self.text_edit.toPlainText().strip(); self.refresh_table(i)
    def split_at_word(self, word_index):
        i=self.selected_index()
        if i<0:return
        it=self.items[i]; tokens=it['text'].split()
        if word_index<=0 or word_index>=len(tokens): self.msg("Vágás","A vágáshoz válassz egy szót a felirat közepén."); return
        word_records=it.get('words', [])
        if len(word_records)==len(tokens):
            mid=(float(word_records[word_index-1]['end'])+float(word_records[word_index]['start']))/2
            left_words=word_records[:word_index]; right_words=word_records[word_index:]
        else:
            ratio=word_index/len(tokens); mid=it['start']+(it['end']-it['start'])*ratio
            left_words=[]; right_words=[]
        self.items[i:i+1]=[{'start':it['start'],'end':mid,'text':' '.join(tokens[:word_index]),'words':left_words},{'start':mid,'end':it['end'],'text':' '.join(tokens[word_index:]),'words':right_words}]
        self.refresh_table(i)
    def split_before_word(self):
        cursor=self.text_edit.textCursor(); pos=cursor.position(); text=self.text_edit.toPlainText(); word_index=len(text[:pos].split())
        self.split_at_word(word_index)
    def split_cursor(self):
        cursor=self.text_edit.textCursor(); pos=cursor.position(); text=self.text_edit.toPlainText()
        left=text[:pos].strip(); right=text[pos:].strip()
        if not left or not right: self.msg("Vágás","Helyezd a kurzort a szöveg két része közé."); return
        i=self.selected_index(); self.split_at_word(len(left.split()))
    def merge(self):
        i=self.selected_index()
        if i<0 or i>=len(self.items)-1: return
        a,b=self.items[i],self.items[i+1]; self.items[i:i+2]=[{'start':a['start'],'end':b['end'],'text':(a['text']+' '+b['text']).strip(),'words':a.get('words',[])+b.get('words',[])}]; self.refresh_table(i)
    def edge_changed(self,i,s,e):
        if i>=len(self.items):return
        self.items[i]['start']=s; self.items[i]['end']=e
        self.timeline.set_data(self.items,self.player.duration()/1000 if self.player.duration() else None)
        for col,val in [(1,f"{s:.3f}"),(2,f"{e:.3f}")]:
            cell=self.table.item(i,col)
            if cell: cell.setText(val)
    def seek_seconds(self,s): self.player.setPosition(int(s*1000))
    def toggle_play(self):
        if self.player.playbackState()==QMediaPlayer.PlayingState:self.player.pause()
        else:self.player.play()
    def position_changed(self,p): self.position.setText(f"{p/1000:.3f}s")
    def duration_changed(self,d): self.timeline.set_data(self.items,d/1000 if d else None)
    def open_project(self):
        path,_=QFileDialog.getOpenFileName(self,"Everest projekt megnyitása","","Everest projekt (*.evss)")
        if not path:return
        try:
            with open(path,'r',encoding='utf-8') as f: data=json.load(f)
            self.items=data.get('items',[])
            media=data.get('media_path')
            self.media_path=media if media and os.path.exists(media) else None
            if self.media_path:self.player.setSource(QUrl.fromLocalFile(self.media_path))
            self.current_project=path; self.refresh_table(); self.status.setText(Path(path).name)
            if not self.media_path:self.msg("Projekt megnyitva","A feliratok betöltődtek, de az eredeti médiafájl nem található. Nyisd meg külön a videót vagy hangfájlt.")
        except Exception as e:
            QMessageBox.critical(self,"Projektmegnyitási hiba",str(e))
    def save_project(self):
        if not self.items: self.msg("Nincs projekt","Először készíts feliratot vagy nyiss meg egy projektet."); return
        path,_=QFileDialog.getSaveFileName(self,"Projekt mentése","","Everest projekt (*.evss)")
        if path:
            if not path.endswith('.evss'):path+='.evss'
            with open(path,'w',encoding='utf-8') as f:json.dump({'media_path':self.media_path,'items':self.items},f,ensure_ascii=False,indent=2)
            self.current_project=path; self.status.setText("Projekt elmentve")
    def export_srt(self):
        if not self.items:self.msg("Nincs felirat","Először készíts feliratot.");return
        default=str(Path(self.media_path).with_suffix('.srt')) if self.media_path else 'felirat.srt'
        path,_=QFileDialog.getSaveFileName(self,"SRT exportálása",default,"SubRip felirat (*.srt)")
        if path:
            if not path.lower().endswith('.srt'):path+='.srt'
            with open(path,'w',encoding='utf-8-sig',newline='\n') as f:
                for i,it in enumerate(self.items,1):f.write(f"{i}\n{srt_time(it['start'])} --> {srt_time(it['end'])}\n{it['text']}\n\n")
            self.status.setText("SRT exportálva")


def main():
    app=QApplication(sys.argv); app.setStyle('Fusion'); app.setStyleSheet(DARK_QSS)
    w=MainWindow(); w.show(); sys.exit(app.exec())
if __name__=='__main__': main()
