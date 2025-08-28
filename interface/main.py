import sqlite3
import os.path
import re
import html
import webbrowser
from datetime import date, timedelta, datetime
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.clock import Clock
from kivy.network.urlrequest import UrlRequest
from urllib.parse import quote_plus
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton
from kivymd.uix.textfield import MDTextField
from kivymd.toast import toast
from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.list import TwoLineAvatarIconListItem, IconRightWidget
from functools import partial
from kivy.metrics import dp
from kivy.loader import Loader
from kivy.core.text import LabelBase
from kivy.resources import resource_add_path
from kivy.core.window import Window
from kivymd.uix.menu import MDDropdownMenu
from kivy.utils import get_color_from_hex
from kivymd.uix.card import MDSeparator
from kivy.uix.relativelayout import RelativeLayout
from kivy.core.window import Window
from kivy.utils import platform
from kivymd.uix.label import MDLabel


# ---------- Graph (kivy-garden.graph) ----------
try:
    # Agora importamos também o MeshStemPlot para "barras"
    from kivy_garden.graph import Graph, MeshLinePlot, MeshStemPlot
    HAS_GRAPH = True
except Exception:
    HAS_GRAPH = False


# ===================== SCREENS =====================
class NoteDetailScreen(Screen):
    note_id = NumericProperty(0)
    book_id = StringProperty("")
    book_title = StringProperty("")
    note_text = StringProperty("")


class NoteEditorScreen(Screen):
    note_id = NumericProperty(0)   # 0 = nova
    book_id = StringProperty("")
    book_title = StringProperty("")
    note_text = StringProperty("")


class BookItem(ButtonBehavior, MDBoxLayout):
    title = StringProperty('')
    cover_url = StringProperty('')
    book_id = StringProperty('')
    authors = StringProperty('')
    page_count = NumericProperty(0)
    description = StringProperty('')
    removable = BooleanProperty(False)


class MainScreen(Screen):
    show_back = BooleanProperty(False)


class GraphScreen(Screen):
    pass


class NotesScreen(Screen):
    notes_book_id = StringProperty("")
    notes_book_title = StringProperty("Selecionar livro")


class TimerScreen(Screen):
    pass


class BookDetailScreen(Screen):
    book_id = StringProperty('')
    book_title = StringProperty('')
    authors = StringProperty('')
    cover_url = StringProperty('')
    page_count = NumericProperty(0)
    description = StringProperty('')
    already_added = BooleanProperty(False)
    pages_read = NumericProperty(0)
    book_status = StringProperty('Quero ler')
    progress_percent = NumericProperty(0)


# ===================== APP =====================
class RootsApp(MDApp):
    APP_BG_COLOR = get_color_from_hex("#1b2c3c")
    READING_GOAL_MIN_PER_DAY = 6  # meta diária (min). Ajuste se quiser.

        # --- MENU DE STATUS NO DETALHE DO LIVRO ---
    def open_status_menu(self, caller):
        # Cria (ou reusa) o dropdown preso ao botão de 3 pontos do AppBar
        try:
            # Fecha menu anterior, se existir
            if hasattr(self, "_status_menu") and self._status_menu:
                self._status_menu.dismiss()
        except Exception:
            pass

        items = [
            {"text": "Quero ler", "on_release": lambda: (self.set_status_from_ui("Quero ler"), self._dismiss_status_menu())},
            {"text": "Lendo",     "on_release": lambda: (self.set_status_from_ui("Lendo"),     self._dismiss_status_menu())},
            {"text": "Lido",      "on_release": lambda: (self.set_status_from_ui("Lido"),      self._dismiss_status_menu())},
        ]
        self._status_menu = MDDropdownMenu(caller=caller, items=items, width_mult=3)
        self._status_menu.open()

    def _dismiss_status_menu(self):
        if hasattr(self, "_status_menu") and self._status_menu:
            try:
                self._status_menu.dismiss()
            except Exception:
                pass
            self._status_menu = None


    # ------------------ FONTS ------------------
    def _register_fonts(self):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            fonts_dir = os.path.join(base_dir, "fonts")
            resource_add_path(fonts_dir)

            LabelBase.register(
                name="Poppins",
                fn_regular=os.path.join(fonts_dir, "Poppins-Regular.ttf"),
                fn_bold=os.path.join(fonts_dir, "Poppins-SemiBold.ttf"),
            )
            LabelBase.register(
                name="Inter",
                fn_regular=os.path.join(fonts_dir, "Inter-Regular.ttf"),
                fn_bold=os.path.join(fonts_dir, "Inter-Medium.ttf"),
            )
        except Exception as e:
            print("[Fonts] Falha ao registrar fontes:", e)

    # ------------------ NAV ------------------
    def go_home(self):
        self.root.current = 'main_screen'

    def go_graph(self):
        self.root.current = 'graph_screen'
        # Renderiza o gráfico de TEMPO (único)
        Clock.schedule_once(lambda *_: self.render_time_chart(), 0)

    def go_notes(self):
        self.root.current = 'notes_screen'
        self.load_notes()

    def go_timer(self):
        self.root.current = 'timer_screen'
        try:
            ts = self.root.get_screen('timer_screen')
            if not getattr(self, "_timer_running", False):
                ts.ids.timer_label.text = "00:00:00"
        except Exception:
            pass

    def on_back_from_search(self):
        sm = self.root.get_screen('main_screen')
        sm.show_back = False
        self.load_saved_books()

    # ------------------ UTILS ------------------
    def notify(self, msg: str):
        try:
            toast(msg)
        except Exception:
            print(msg)

    @staticmethod
    def _normalize_text(s: str) -> str:
        s = (s or "").lower().strip()
        s = re.sub(r"[\s\-\_\.\,\:\;\!\?\(\)\[\]\{\}]+", " ", s)
        s = re.sub(r"\s+", " ", s)
        return s

    @staticmethod
    def clean_description(s: str) -> str:
        s = s or ''
        s = re.sub(r'<[^>]+>', '', s)
        return html.unescape(s).strip()

    # ------------------ APP LIFECYCLE ------------------
    def build(self):
        # Define o tema como Escuro
        self.theme_cls.theme_style = "Dark"
        
        # Define a cor primária (botões, barras, etc.) para o Marrom Tronco
        # KivyMD usa nomes de paletas, "Brown" é o mais próximo do seu #794428
        self.theme_cls.primary_palette = "Brown"
        self.theme_cls.primary_hue = "800" # Um tom de marrom mais forte e escuro
        
        self.initialize_database()
        self._register_fonts()
        Window.clearcolor = self.APP_BG_COLOR
        return Builder.load_file('ui.kv')

    def initialize_database(self):
        db_dir = os.path.join(self.user_data_dir, "db")
        os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(os.path.join(db_dir, "roots.db"))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS livros (
                id TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                autor TEXT,
                cover_url TEXT,
                qtde_paginas INTEGER,
                status TEXT CHECK(status IN ('Lendo', 'Concluído', 'Quero ler')) DEFAULT 'Quero ler',
                pagina_atual INTEGER DEFAULT 0,
                nota INTEGER DEFAULT 0,
                genero_id INTEGER,
                descricao TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL UNIQUE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS progresso_diario (
                livro_id TEXT,
                data TEXT,
                paginas_lidas INTEGER
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS anotacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                livro_id TEXT,
                texto TEXT
            )
        """)

        # ATENÇÃO: livro_id sem NOT NULL para evitar erro ao salvar sessão sem escolher livro
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessoes_leitura (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                livro_id TEXT,
                inicio TEXT NOT NULL,
                fim TEXT NOT NULL,
                duracao_seg INTEGER NOT NULL,
                dia TEXT NOT NULL
            )
        """)

        conn.commit()
        conn.close()

    def on_start(self):
        self.load_saved_books()
        self.load_notes()
        # (gráfico só quando abre a tela de gráficos)

    # ------------------ DETALHES (livro) ------------------
    def is_book_saved(self, book_id, title, authors) -> bool:
        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT 1 FROM livros WHERE id = ? LIMIT 1", (book_id,))
            return cursor.fetchone() is not None
        finally:
            conn.close()

    def open_book_detail(self, book_id, title, authors, cover_url, page_count, description=''):
        detail = self.root.get_screen('detail_screen')

        detail.book_id = book_id
        detail.book_title = title
        detail.authors = authors
        detail.cover_url = cover_url
        detail.page_count = int(page_count or 0)
        detail.description = description or ''
        detail.already_added = self.is_book_saved(book_id, title, authors)

        # --- INÍCIO DA CORREÇÃO ---
        # Pega os widgets pelo ID que definimos no arquivo .kv
        progress_layout = detail.ids.progress_layout
        separator = detail.ids.separator

        # Lógica para mostrar ou esconder a barra de progresso
        if detail.already_added:
            # Se o livro está na biblioteca, mostra a barra e o separador
            progress_layout.opacity = 1
            progress_layout.height = progress_layout.minimum_height
            progress_layout.size_hint_y = None
            
            separator.opacity = 1
            separator.height = dp(1)
            
            # Carrega os dados do banco de dados
            Clock.schedule_once(lambda *_: self._hydrate_detail_from_db(book_id), 0)
        else:
            # Se o livro NÃO está na biblioteca, esconde a barra e o separador
            progress_layout.opacity = 0
            progress_layout.height = 0
            progress_layout.size_hint_y = None

            separator.opacity = 0
            separator.height = 0
            
            # Reseta os valores para um livro não salvo
            detail.pages_read = 0
            detail.book_status = 'Quero ler'
            self._refresh_detail_progress()
        # --- FIM DA CORREÇÃO ---

        self.root.current = 'detail_screen'

    def _hydrate_detail_from_db(self, book_id):
        detail = self.root.get_screen('detail_screen')
        if not detail.already_added:
            return

        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT COALESCE(pagina_atual,0),
                       COALESCE(status,'Quero ler'),
                       COALESCE(qtde_paginas,0)
                FROM livros WHERE id = ?
            """, (book_id,))
            row = cur.fetchone()
        finally:
            conn.close()

        if row:
            detail.pages_read = int(row[0] or 0)
            detail.book_status = row[1] or 'Quero ler'
            if (row[2] or 0) > 0:
                detail.page_count = int(row[2])
            self._refresh_detail_progress()

    def save_from_detail(self):
        def _do_save(*_):
            try:
                detail = self.root.get_screen('detail_screen')
                ok = self.save_book_to_database(
                    detail.book_id, detail.book_title, detail.authors,
                    detail.cover_url, detail.page_count, detail.description or ''
                )
                if ok:
                    self.notify(f"'{detail.book_title}' adicionado à sua lista!")
                    self.go_home()
            except Exception as e:
                import traceback; traceback.print_exc()
                self.notify(f"Falha ao adicionar: {e}")

        Clock.schedule_once(_do_save, 0)

    # ------------------ BUSCA ------------------
    def add_book_search(self, query):
        sm = self.root.get_screen('main_screen')
        books_grid = sm.ids.books_grid
        books_grid.clear_widgets()

        q = (query or "").strip()
        if not q:
            self.notify("Digite algo para buscar.")
            sm.show_back = False
            return

        sm.show_back = True

        api_url = (
            "https://www.googleapis.com/books/v1/volumes"
            f"?q={quote_plus(q)}"
            "&printType=books"
            "&orderBy=relevance"
            "&maxResults=30"
            "&langRestrict=pt"
        )

        seen_ids = set()
        seen_title_author = set()

        def ok(req, result):
            added = 0
            items = (result or {}).get('items') or []
            for item in items:
                volume_info = item.get('volumeInfo', {}) or {}
                book_id = item.get('id', '')
                title = volume_info.get('title', 'Título Desconhecido') or ""
                authors_list = volume_info.get('authors', ['Autor Desconhecido'])
                authors = ', '.join(authors_list)
                cover_url = (volume_info.get('imageLinks', {}) or {}).get('thumbnail', '') or ""
                page_count = volume_info.get('pageCount', 0) or 0
                description = volume_info.get('description', '') or ''

                if not cover_url:
                    continue

                if book_id and book_id in seen_ids:
                    continue
                ta_key = f"{self._normalize_text(title)}|{self._normalize_text(authors)}"
                if ta_key in seen_title_author:
                    continue

                if book_id:
                    seen_ids.add(book_id)
                seen_title_author.add(ta_key)

                books_grid.add_widget(BookItem(
                    book_id=book_id,
                    title=title,
                    authors=authors,
                    cover_url=cover_url,
                    page_count=page_count,
                    description=description,
                    removable=False
                ))
                added += 1

            if added == 0:
                self.notify("Nada encontrado.")
                sm.show_back = False
            else:
                sm.show_back = True

        def fail(req, err):
            print("Erro na busca:", err)
            sm.show_back = False
            self.notify("Erro ao buscar livros, Verifique sua conexão.")

        UrlRequest(api_url, on_success=ok, on_error=fail, on_failure=fail, decode=True)

    # ------------------ DB: livros ------------------
    def save_book_to_database(self, book_id, title, authors, cover_url, page_count, description=''):
        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            page_count = int(page_count) if page_count is not None else 0
        except (ValueError, TypeError):
            page_count = 0

        try:
            cursor.execute("""
                INSERT OR IGNORE INTO livros (
                    id, nome, autor, cover_url, qtde_paginas, status, pagina_atual, nota, genero_id, descricao
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (book_id, title, authors, cover_url, page_count, 'Quero ler', 0, 0, None, description))
            conn.commit()
            self.load_saved_books()
            self.notify(f"'{title}' adicionado à sua lista!")
            return True
        except sqlite3.Error as e:
            print(f"Erro ao salvar livro: {e}")
            return False
        finally:
            conn.close()

    def load_saved_books(self):
        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, nome, autor, cover_url, COALESCE(qtde_paginas,0), COALESCE(descricao,'')
            FROM livros
            ORDER BY rowid DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        grid = self.root.get_screen('main_screen').ids.books_grid
        grid.clear_widgets()
        self.root.get_screen('main_screen').show_back = False

        seen = set()
        for book_id, title, authors, cover_url, page_count, description in rows:
            key = f"{self._normalize_text(title)}|{self._normalize_text(authors)}"
            if key in seen:
                continue
            seen.add(key)

            grid.add_widget(BookItem(
                book_id=book_id,
                title=title,
                authors=authors,
                cover_url=cover_url,
                page_count=page_count,
                description=description,
                removable=True
            ))

            if cover_url:
                Loader.image(cover_url)

    def delete_book(self, book_id, title=None):
        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM progresso_diario WHERE livro_id = ?", (book_id,))
            cursor.execute("DELETE FROM anotacoes WHERE livro_id = ?", (book_id,))
            cursor.execute("DELETE FROM livros WHERE id = ?", (book_id,))
            conn.commit()
            self.load_saved_books()
            self.notify(f"'{title}' removido." if title else "Livro removido.")
        except sqlite3.Error as e:
            print(f"Erro ao remover livro: {e}")
            self.notify("Falha ao remover.")
        finally:
            conn.close()

    # ------------------ GRÁFICO: TEMPO DE LEITURA ------------------
    def _week_range_sun_sat(self):
        """
        Retorna (start, end) da semana DOM->SÁB da data atual.
        """
        today = date.today()
        days_since_sun = (today.weekday() + 1) % 7  # dom -> 0
        start = today - timedelta(days=days_since_sun)
        end = start + timedelta(days=6)
        return start, end

    def render_time_chart(self):
        """
        Gráfico ÚNICO: TEMPO de leitura na semana atual (Dom-Sáb).
        Usa os recursos do próprio Graph para desenhar os rótulos dos dias,
        garantindo o alinhamento perfeito.
        """
        from kivymd.uix.boxlayout import MDBoxLayout
        from kivymd.uix.label import MDLabel
        from kivymd.uix.card import MDSeparator

        try:
            gs = self.root.get_screen('graph_screen')
            box = gs.ids.chart_time
        except Exception:
            return

        box.clear_widgets()

        start, end = self._week_range_sun_sat()

        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT date(COALESCE(dia, inicio)) AS d,
                   SUM(COALESCE(duracao_seg, 0)) AS segs
            FROM sessoes_leitura
            WHERE date(COALESCE(dia, inicio)) BETWEEN ? AND ?
            GROUP BY date(COALESCE(dia, inicio))
            ORDER BY d
        """, (start.isoformat(), end.isoformat()))
        rows = dict(cur.fetchall())
        conn.close()

        xs, ys = [], []
        d = start
        for i in range(7):
            xs.append(i)
            secs = int(rows.get(d.isoformat(), 0))
            mins = secs // 60
            ys.append(mins)
            d += timedelta(days=1)

        y_max = 120
        y_tick = 30

        box.add_widget(MDLabel(text="Tempo de leitura (min) — semana atual (Dom->Sáb)",
                               halign="center", size_hint_y=None, height=dp(24), bold=True))

        if not HAS_GRAPH:
            return
        
        graph = Graph(
            xlabel='Dias',
            ylabel='Minutos',
            x_ticks_minor=0,
            y_ticks_major=y_tick, 
            y_grid_label=True,
            x_grid=True, 
            y_grid=True,
            xmin=-0.5, 
            xmax=6.5,
            ymin=0, 
            ymax=y_max,
            size_hint=(1, None), 
            height=dp(260),
            padding=dp(5) 
        )

        week_days = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
        graph.x_ticks_major = 1  
        graph.x_labels = [week_days[i] for i in range(7)] 


        try:
            bar_plot = MeshStemPlot(color=self.theme_cls.primary_color)
            bar_plot.points = list(zip(xs, ys))
            graph.add_plot(bar_plot)
        except Exception:
            line_fallback = MeshLinePlot(color=self.theme_cls.primary_color)
            line_fallback.points = list(zip(xs, ys))
            graph.add_plot(line_fallback)

        media = sum(ys) / 7.0 if ys else 0.0
        avg_plot = MeshLinePlot(color=[1, 0, 0, 0.7])
        avg_plot.points = [(x, media) for x in xs]
        graph.add_plot(avg_plot)

        box.add_widget(graph)

        day_labels_layout = MDBoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(20),
            padding=(dp(68), 0, dp(10), 0)
        )

        week_days = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
        for label in week_days:
            day_labels_layout.add_widget(MDLabel(text=label, halign='center'))

        box.add_widget(day_labels_layout)

        box.add_widget(MDLabel(
            text=f"Média: {media:.1f} min/dia",
            halign="center",
            size_hint_y=None,
            height=dp(22),
            theme_text_color="Secondary"
        ))

        box.add_widget(MDBoxLayout(size_hint_y=None, height=dp(20)))
        box.add_widget(MDSeparator())
        box.add_widget(MDBoxLayout(size_hint_y=None, height=dp(10)))

        total_minutes = sum(ys)
        max_minutes = max(ys) if ys else 0
        min_minutes = min(ys) if ys else 0
        
        most_productive_day = week_days[ys.index(max_minutes)] if total_minutes > 0 else "Nenhum"
        least_productive_day = week_days[ys.index(min_minutes)] if total_minutes > 0 else "Nenhum"

        total_label = MDLabel(
            text=f"Total de minutos lidos na semana: [b]{total_minutes}[/b]",
            halign="center", size_hint_y=None, height=dp(20), markup=True
        )
        max_day_label = MDLabel(
            text=f"Dia mais produtivo: [b]{most_productive_day}[/b] ({max_minutes} min)",
            halign="center", size_hint_y=None, height=dp(20), markup=True
        )
        min_day_label = MDLabel(
            text=f"Dia com menor leitura: [b]{least_productive_day}[/b] ({min_minutes} min)",
            halign="center", size_hint_y=None, height=dp(20), markup=True
        )

        box.add_widget(total_label)
        box.add_widget(max_day_label)
        box.add_widget(min_day_label)

    # ------------------ ANOTAÇÕES ------------------
    def open_book_picker(self):
        ns = self.root.get_screen('notes_screen')
        btn = ns.ids.book_select_btn

        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome FROM livros ORDER BY nome COLLATE NOCASE ASC")
        books = cursor.fetchall()
        conn.close()

        items = [{"text": "Todos", "on_release": lambda: self._pick_book_for_note("", "Todos")}]
        if books:
            items += [{
                "text": title,
                "on_release": (lambda b_id=bid, t=title: self._pick_book_for_note(b_id, t))
            } for bid, title in books]

        self._notes_menu = MDDropdownMenu(caller=btn, items=items, width_mult=4)
        self._notes_menu.open()

    def _pick_book_for_note(self, book_id, title):
        ns = self.root.get_screen('notes_screen')
        ns.notes_book_id = book_id or ""
        ns.notes_book_title = title if book_id else "Todos"
        if getattr(self, "_notes_menu", None):
            self._notes_menu.dismiss()

    def apply_notes_filter(self):
        ns = self.root.get_screen('notes_screen')
        bid = (ns.notes_book_id or "").strip()
        self.load_notes(filter_book_id=bid if bid else None)

    def create_note_for_selected_book(self):
        ns = self.root.get_screen('notes_screen')
        bid = (ns.notes_book_id or "").strip()
        if not bid:
            self.notify("Selecione um livro para criar a anotação.")
            return
        self.open_note_editor(note_id=0, book_id=bid, book_title=ns.notes_book_title, note_text="")

    def load_notes(self, filter_book_id=None):
        ns = self.root.get_screen('notes_screen')
        lst = ns.ids.notes_list
        lst.clear_widgets()

        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        if filter_book_id:
            cursor.execute("""
                SELECT a.id, COALESCE(l.nome, 'Sem livro'), a.texto, a.livro_id
                FROM anotacoes a
                LEFT JOIN livros l ON l.id = a.livro_id
                WHERE a.livro_id = ?
                ORDER BY a.id DESC
            """, (filter_book_id,))
        else:
            cursor.execute("""
                SELECT a.id, COALESCE(l.nome, 'Sem livro'), a.texto, a.livro_id
                FROM anotacoes a
                LEFT JOIN livros l ON l.id = a.livro_id
                ORDER BY a.id DESC
            """)
        rows = cursor.fetchall()
        conn.close()

        for note_id, book_title, text, livro_id in rows:
            preview = (text or "").replace("\n", " ")
            if len(preview) > 80:
                preview = preview[:80] + "…"

            item = TwoLineAvatarIconListItem(text=book_title, secondary_text=preview)
            item.bind(on_release=partial(self.open_note_detail, note_id))
            item.add_widget(IconRightWidget(icon="pencil", on_release=partial(self.open_note_editor, note_id)))
            item.add_widget(IconRightWidget(icon="delete", on_release=partial(self.delete_note_confirm, note_id)))
            lst.add_widget(item)

    def open_note_detail(self, note_id, *args):
        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.id, a.texto, COALESCE(l.id,''), COALESCE(l.nome,'Sem livro')
            FROM anotacoes a
            LEFT JOIN livros l ON l.id = a.livro_id
            WHERE a.id = ?
        """, (note_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            self.notify("Anotação não encontrada.")
            return

        note_detail = self.root.get_screen('note_detail')
        note_detail.note_id = int(row[0])
        note_detail.note_text = row[1] or ""
        note_detail.book_id = row[2] or ""
        note_detail.book_title = row[3] or "Sem livro"
        self.root.current = 'note_detail'

    def open_note_editor(self, note_id=0, *args, book_id="", book_title="", note_text=""):
        editor = self.root.get_screen('note_editor')

        if note_id:
            db_path = os.path.join(self.user_data_dir, "db", "roots.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.id, a.texto, COALESCE(l.id,''), COALESCE(l.nome,'Sem livro')
                FROM anotacoes a
                LEFT JOIN livros l ON l.id = a.livro_id
                WHERE a.id = ?
            """, (note_id,))
            row = cursor.fetchone()
            conn.close()
            if not row:
                self.notify("Anotação não encontrada.")
                return
            editor.note_id = int(row[0])
            editor.note_text = row[1] or ""
            editor.book_id = row[2] or ""
            editor.book_title = row[3] or "Sem livro"
        else:
            editor.note_id = 0
            editor.note_text = note_text or ""
            editor.book_id = book_id or ""
            editor.book_title = book_title or "Sem livro"

        editor.ids.editor_text.text = editor.note_text
        self.root.current = 'note_editor'

    def save_note_from_editor(self):
        editor = self.root.get_screen('note_editor')
        text = (editor.ids.editor_text.text or "").strip()
        if not text:
            self.notify("Escreva algo na anotação.")
            return

        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            if editor.note_id:  # editar
                cursor.execute(
                    "UPDATE anotacoes SET texto = ?, livro_id = ? WHERE id = ?",
                    (text, editor.book_id or None, editor.note_id)
                )
                note_id = editor.note_id
            else:  # criar
                if not editor.book_id:
                    self.notify("Selecione um livro para a nova anotação.")
                    conn.close()
                    return
                cursor.execute(
                    "INSERT INTO anotacoes (livro_id, texto) VALUES (?, ?)",
                    (editor.book_id, text)
                )
                note_id = cursor.lastrowid
            conn.commit()
        except sqlite3.Error as e:
            print("Erro ao salvar anotação:", e)
            self.notify("Erro ao salvar anotação.")
            conn.close()
            return
        conn.close()

        self.load_notes()
        self.open_note_detail(note_id)

    def delete_note_confirm(self, note_id, *args):
        self._pending_delete_note_id = int(note_id)

        def _do_delete(*_):
            nid = getattr(self, "_pending_delete_note_id", 0)
            if not nid:
                return
            db_path = os.path.join(self.user_data_dir, "db", "roots.db")
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            try:
                cur.execute("DELETE FROM anotacoes WHERE id = ?", (nid,))
                conn.commit()
            except sqlite3.Error as e:
                print("Erro ao apagar anotação:", e)
                self.notify("Falha ao apagar anotação.")
                conn.close()
                return
            conn.close()
            self.notify("Anotação apagada.")
            self._pending_delete_note_id = 0
            if self.root.current == 'note_detail':
                self.go_notes()
            else:
                self.load_notes()

            self._dismiss_delete_dialog()

        self._delete_dialog = MDDialog(
            title="Apagar anotação",
            text="Tem certeza que deseja apagar esta anotação?",
            buttons=[
                MDFlatButton(text="Cancelar", on_release=lambda *_: self._dismiss_delete_dialog()),
                MDFlatButton(text="Apagar", on_release=_do_delete),
            ],
        )
        self._delete_dialog.open()

    def _dismiss_delete_dialog(self):
        dlg = getattr(self, "_delete_dialog", None)
        if dlg:
            dlg.dismiss()
        self._delete_dialog = None

    # ------------------ STATUS / PROGRESSO ------------------
    def status_db_to_ui(self, s: str) -> str:
        m = {"Concluído": "Lido", "Lendo": "Lendo", "Quero ler": "Quero ler"}
        return m.get((s or "").strip(), "Quero ler")

    def status_ui_to_db(self, s: str) -> str:
        m = {"Lido": "Concluído", "Lendo": "Lendo", "Quero ler": "Quero ler"}
        return m.get((s or "").strip(), "Quero ler")

    def status_ui(self, status_db: str) -> str:
        return self.status_db_to_ui(status_db)

    def set_status_from_ui(self, ui_status: str):
        detail = self.root.get_screen('detail_screen')
        if not detail.already_added:
            self.notify("Adicione o livro primeiro.")
            return

        s_db = self.status_ui_to_db(ui_status)
        pc = int(detail.page_count or 0)
        self.update_book_status(s_db, pc, detail)

    def update_book_progress(self, new_pages_read: int):
        detail = self.root.get_screen('detail_screen')
        pc = int(detail.page_count or 0)
        old_pages = int(detail.pages_read or 0)

        # Garante que o novo valor de páginas lidas esteja dentro dos limites (0 a page_count)
        if pc > 0:
            new_pages = max(0, min(int(new_pages_read or 0), pc))
        else:
            new_pages = 0

        # Define o status com base no novo número de páginas
        if new_pages <= 0:
            status = 'Quero ler'
            new_pages = 0
        elif pc > 0 and new_pages >= pc:
            status = 'Concluído'
            new_pages = pc
        else:
            status = 'Lendo'

        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        try:
            # 1. Salva o estado principal (página e status) SEMPRE.
            cur.execute(
                "UPDATE livros SET pagina_atual = ?, status = ? WHERE id = ?",
                (new_pages, status, detail.book_id)
            )

            # 2. Calcula o delta e salva o progresso diário APENAS se for um avanço.
            delta = new_pages - old_pages
            if delta > 0:
                today = date.today().isoformat()
                # Usamos INSERT OR IGNORE e UPDATE para lidar com o registro diário
                cur.execute(
                    "INSERT OR IGNORE INTO progresso_diario (livro_id, data, paginas_lidas) VALUES (?, ?, 0)",
                    (detail.book_id, today)
                )
                cur.execute(
                    "UPDATE progresso_diario SET paginas_lidas = paginas_lidas + ? WHERE livro_id = ? AND data = ?",
                    (delta, detail.book_id, today)
                )
            
            conn.commit()

        except sqlite3.Error as e:
            print("Erro ao atualizar progresso:", e)
            self.notify("Não consegui salvar o progresso.")
        finally:
            conn.close()

        # Atualiza as propriedades da tela para refletir a mudança imediatamente
        detail.pages_read = new_pages
        detail.book_status = status
        self._refresh_detail_progress()  # Recalcula a porcentagem e atualiza a UI
        self.notify("Progresso atualizado.")

    def _refresh_detail_progress(self):
        detail = self.root.get_screen('detail_screen')
        pc = int(detail.page_count or 0)
        pr = int(detail.pages_read or 0)
        if pc <= 0:
            detail.progress_percent = 0
            return
        pr = max(0, min(pr, pc))
        detail.pages_read = pr
        detail.progress_percent = int(round((pr / pc) * 100))

        if pr == 0:
            detail.book_status = 'Quero ler'
        elif pr >= pc:
            detail.book_status = 'Concluído'
        else:
            if detail.book_status not in ('Lendo', 'Concluído'):
                detail.book_status = 'Lendo'

    def prompt_update_progress(self):
        detail = self.root.get_screen('detail_screen')
        if not detail.already_added:
            self.notify("Adicione o livro para acompanhar o progresso.")
            return

        field = MDTextField(
            text=str(detail.pages_read or 0),
            hint_text="Páginas lidas",
            input_filter="int"
        )

        self._progress_dialog = MDDialog(
            title="Atualizar progresso",
            type="custom",
            content_cls=field,
            buttons=[
                MDFlatButton(text="Cancelar", on_release=lambda *_: self._dismiss_progress_dialog()),
                MDFlatButton(text="Salvar", on_release=lambda *_: self._save_progress_from_dialog(field.text)),
            ],
        )
        self._progress_dialog.open()

    def _dismiss_progress_dialog(self):
        dlg = getattr(self, "_progress_dialog", None)
        if dlg:
            dlg.dismiss()
        self._progress_dialog = None

    def _save_progress_from_dialog(self, txt):
        self._dismiss_progress_dialog()
        try:
            new_val = int(txt or 0)
        except ValueError:
            self.notify("Valor inválido.")
            return
        self.update_book_progress(new_val)

    def update_book_progress(self, new_pages_read: int):
        detail = self.root.get_screen('detail_screen')
        pc = int(detail.page_count or 0)
        old_pages = int(detail.pages_read or 0)
        new_pages = max(0, min(int(new_pages_read or 0), pc))

        if new_pages == 0:
            status = 'Quero ler'
        elif pc > 0 and new_pages >= pc:
            status = 'Concluído'
        else:
            status = 'Lendo'

        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE livros SET pagina_atual = ?, status = ? WHERE id = ?",
                (new_pages, status, detail.book_id)
            )

            delta = max(0, new_pages - old_pages)
            if delta > 0:
                today = date.today().isoformat()
                cur.execute(
                    "INSERT INTO progresso_diario (livro_id, data, paginas_lidas) VALUES (?, ?, ?)",
                    (detail.book_id, today, delta)
                )
            conn.commit()
        except sqlite3.Error as e:
            print("Erro ao atualizar progresso:", e)
            self.notify("Não consegui salvar o progresso.")
        finally:
            conn.close()

        detail.pages_read = new_pages
        detail.book_status = status
        self._refresh_detail_progress()
        self.notify("Progresso atualizado.")

    # ------------------ CRONÔMETRO ------------------
    _timer_event = None
    _timer_running = False
    _timer_start_ts = 0

    def _fmt_hhmmss(self, secs: int) -> str:
        secs = max(0, int(secs))
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def start_timer(self):
        if self._timer_running:
            return
        self._timer_running = True
        from time import time
        self._timer_start_ts = int(time())
        if self._timer_event:
            try:
                self._timer_event.cancel()
            except Exception:
                pass
        self._timer_event = Clock.schedule_interval(self._tick_timer, 1)
        self.notify("Cronômetro iniciado.")

    def _tick_timer(self, dt):
        try:
            from time import time
            elapsed = int(time()) - int(self._timer_start_ts or 0)
            ts = self.root.get_screen('timer_screen')
            ts.ids.timer_label.text = self._fmt_hhmmss(elapsed)
        except Exception:
            pass

    def stop_timer(self):
        if not self._timer_running:
            return
        self._timer_running = False
        if self._timer_event:
            try:
                self._timer_event.cancel()
            except Exception:
                pass
            self._timer_event = None
        self.notify("Cronômetro parado.")

    def save_timer(self):
        """Salva a sessão do cronômetro em sessoes_leitura e atualiza o gráfico se estiver na aba."""
        ts = self.root.get_screen('timer_screen')
        txt = ts.ids.timer_label.text.strip() if 'timer_label' in ts.ids else "00:00:00"
        try:
            h, m, s = [int(x) for x in txt.split(":")]
            duracao = h * 3600 + m * 60 + s
        except Exception:
            duracao = 0

        if duracao <= 0:
            self.notify("Nada para salvar.")
            return

        now = datetime.now()
        inicio = now.strftime("%Y-%m-%d %H:%M:%S")
        fim = inicio
        dia = now.date().isoformat()

        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        try:
            # livro_id pode ficar vazio
            cur.execute("""
                INSERT INTO sessoes_leitura (livro_id, inicio, fim, duracao_seg, dia)
                VALUES (?, ?, ?, ?, ?)
            """, ("", inicio, fim, int(duracao), dia))
            conn.commit()
        except Exception as e:
            print("Erro ao salvar sessão:", e)
            self.notify("Falha ao salvar sessão.")
            conn.close()
            return
        conn.close()

        ts.ids.timer_label.text = "00:00:00"
        self.notify("Sessão salva.")

        # Se o usuário estiver na tela de gráficos, atualiza na hora
        if self.root.current == 'graph_screen':
            self.render_time_chart()

    #========== COMPARTILHAMENTO DO GRÁFICO =============

    def share_weekly_summary(self):
        """
        Exporta o layout visível da tela de gráficos como uma imagem PNG
        e abre o gerenciador de arquivos para o usuário compartilhar.
        """
        try:
            # 1. Pega a tela de gráficos atual
            graph_screen = self.root.get_screen('graph_screen')
            
            # 2. Pega o container principal da tela pelo ID que definimos no .kv
            widget_to_export = graph_screen.ids.graph_layout_container
            
            # 3. Define o caminho do arquivo
            filepath = os.path.join(self.user_data_dir, "resumo_semanal.png")
            
            # 4. Exporta o widget diretamente para o arquivo PNG
            widget_to_export.export_to_png(filepath)
            
            # 5. Abre a pasta onde a imagem foi salva
            folder_path = os.path.dirname(filepath)
            webbrowser.open(f"file:///{folder_path}")
            
            self.notify("Imagem salva! Escolha na galeria para compartilhar.")

        except Exception as e:
            print(f"Erro ao criar imagem para compartilhar: {e}")
            self.notify("Ocorreu um erro ao gerar a imagem.")
            
if __name__ == "__main__":
    RootsApp().run()
