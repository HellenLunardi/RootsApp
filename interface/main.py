import sqlite3
import os.path
import re
import html
from datetime import date, timedelta
from kivy.properties import StringProperty, NumericProperty, BooleanProperty, OptionProperty
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
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.list import TwoLineAvatarIconListItem, IconRightWidget
from functools import partial
from kivy.metrics import dp
from kivy.loader import Loader
from pathlib import Path
from kivy.core.text import LabelBase
from kivy.resources import resource_add_path
from kivy.core.window import Window

try:
    from kivy_garden.graph import Graph, MeshLinePlot
    HAS_GRAPH = True
except Exception:
    HAS_GRAPH = False

from kivymd.uix.menu import MDDropdownMenu

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


class RootsApp(MDApp):
    APP_BG_COLOR = (146/255, 216/255, 255/255, 1)

    def _register_fonts(self):
        import os
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
        # desenha/atualiza o gráfico quando entrar
        self.render_reading_chart(days=7)

    def go_notes(self):
        self.root.current = 'notes_screen'
        # carrega as anotações quando entrar
        self.load_notes()

    def on_back_from_search(self):
        """Sai do modo busca na home e recarrega a biblioteca salva."""
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
                descricao TEXT,
                FOREIGN KEY (genero_id) REFERENCES generos(id)
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
                paginas_lidas INTEGER,
                FOREIGN KEY (livro_id) REFERENCES livros(id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS anotacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                livro_id TEXT,
                texto TEXT,
                FOREIGN KEY (livro_id) REFERENCES livros(id)
            )
        """)

        conn.commit()
        conn.close()

    def on_start(self):
        self.load_saved_books()
        # Pré-renderiza dados das outras telas (opcional)
        self.render_reading_chart(days=7)
        self.load_notes()

    # ------------------ DETALHES ------------------

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

        # Preenche o mínimo para abrir a tela já renderizada
        detail.book_id = book_id
        detail.book_title = title
        detail.authors = authors
        detail.cover_url = cover_url
        detail.page_count = int(page_count or 0)
        detail.description = description or ''
        detail.already_added = self.is_book_saved(book_id, title, authors)

        # Progresso básico enquanto carrega
        if detail.already_added:
            # mantém o que já tem salvo numa visita anterior (se houver), senão zera
            pass
        else:
            detail.pages_read = 0
            detail.book_status = 'Quero ler'
        self._refresh_detail_progress()

        # Mostra a tela imediatamente
        self.root.current = 'detail_screen'

        # Hidrata com DB no próximo frame (fora do caminho da animação)
        Clock.schedule_once(lambda *_: self._hydrate_detail_from_db(book_id), 0)

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
                if not cover_url:
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

    # ------------------ GRÁFICO ------------------

    def render_reading_chart(self, days=7):
        from kivymd.uix.boxlayout import MDBoxLayout
        from kivymd.uix.label import MDLabel
        # se você já importou dp no topo (kivy.metrics import dp), pode usar direto aqui

        gs = self.root.get_screen('graph_screen')
        box = gs.ids.chart_box
        box.clear_widgets()

        end = date.today()
        start = end - timedelta(days=days - 1)

        # Busca dados agregados por dia
        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date(data) AS d, SUM(COALESCE(paginas_lidas, 0)) AS pag
            FROM progresso_diario
            WHERE date(data) BETWEEN ? AND ?
            GROUP BY date(data)
            ORDER BY d
        """, (start.isoformat(), end.isoformat()))
        rows = dict(cursor.fetchall())
        conn.close()

        # Monta série contínua
        xs, ys, dates = [], [], []
        d = start
        i = 0
        while d <= end:
            xs.append(i)
            ys.append(int(rows.get(d.isoformat(), 0)))
            dates.append(d)
            i += 1
            d += timedelta(days=1)

        total = sum(ys)
        avg = (total / len(ys)) if ys else 0.0

        # Caso não tenha o garden.graph instalado
        if not HAS_GRAPH:
            box.add_widget(MDLabel(
                text=(f"Gráfico indisponível (instale kivy-garden + garden graph).\n\n"
                    f"Últimos {days} dias — Total: {total} | Média/dia: {avg:.1f}"),
                halign="center"
            ))
            # Linha de rótulos dos dias da semana (fallback visual)
            row = MDBoxLayout(orientation='horizontal', size_hint_y=None, height=dp(20), spacing=0)
            pt = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
            for dt in dates:
                row.add_widget(MDLabel(text=pt[dt.weekday()], halign='center'))
            box.add_widget(row)
            return

        # ----- Com o Graph -----
        # Margem de topo para caber a linha de média com folga
        y_max_base = max(ys + [avg]) if ys else 1
        # dá um “respiro” no topo
        y_max = max(1, int(round(y_max_base + max(1, y_max_base * 0.15))))
        y_tick = max(1, int(round(y_max / 5)))

        graph = Graph(
            xlabel='Dias', ylabel='Páginas',
            x_ticks_minor=0,
            x_ticks_major=1,          # 1 dia por marca
            y_ticks_major=y_tick,
            x_grid=True, y_grid=True,
            xmin=-0.5, xmax=(len(xs) - 0.5) if xs else 0.5,
            ymin=0, ymax=y_max,
            size_hint=(1, None), height=dp(240),
        )

        # Série de leitura (páginas/dia)
        line = MeshLinePlot(color=[0, 0.4, 1, 1])
        line.points = list(zip(range(len(ys)), ys))
        graph.add_plot(line)

        # Linha de MÉDIA horizontal
        avg_plot = MeshLinePlot(color=[1, 0, 0, 1])
        avg_plot.points = [(x, avg) for x in range(len(ys))]
        graph.add_plot(avg_plot)

        box.add_widget(graph)

        # Rótulos com dias da semana alinhados abaixo do gráfico
        row = MDBoxLayout(orientation='horizontal', size_hint_y=None, height=dp(20), spacing=0, padding=(dp(8), 0))
        pt = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        for dt in dates:
            # cada label ocupa a mesma fração da largura
            lbl = MDLabel(text=pt[dt.weekday()], halign='center')
            row.add_widget(lbl)
        box.add_widget(row)

        # Mostra a média num texto auxiliar
        box.add_widget(MDLabel(
            text=f"Média: {avg:.1f} pág/dia",
            halign="center",
            size_hint_y=None,
            height=dp(20),
            theme_text_color="Secondary"
        ))


      # ------------------ ANOTAÇÕES (NOVO FLUXO) ------------------

    def open_book_picker(self):
        ns = self.root.get_screen('notes_screen')
        btn = ns.ids.book_select_btn

        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome FROM livros ORDER BY nome COLLATE NOCASE ASC")
        books = cursor.fetchall()
        conn.close()

        items = [
        {
            "text": "Todos",
            "on_release": lambda: self._pick_book_for_note("", "Todos"),
        }
        ]
        
        if books:
            items += [{
                "text": title,
                "on_release": (lambda b_id=bid, t=title: self._pick_book_for_note(b_id, t))
            } for bid, title in books]
        else:
            items += [{
                "text": "Todos",
                "on_release": lambda: self._pick_book_for_note("", "Todos")
            }]


        self._notes_menu = MDDropdownMenu(caller=btn, items=items, width_mult=4)
        self._notes_menu.open()

    def _pick_book_for_note(self, book_id, title):
        ns = self.root.get_screen('notes_screen')
        ns.notes_book_id = book_id or ""
        ns.notes_book_title = title if book_id else "Todos"
        if getattr(self, "_notes_menu", None):
            self._notes_menu.dismiss()

    def apply_notes_filter(self):
        """Filtra a lista de notas pelo livro selecionado."""
        ns = self.root.get_screen('notes_screen')
        bid = (ns.notes_book_id or "").strip()
        self.load_notes(filter_book_id=bid if bid else None)

    def create_note_for_selected_book(self):
        """Abre o editor para criar nota do livro selecionado."""
        ns = self.root.get_screen('notes_screen')
        bid = (ns.notes_book_id or "").strip()
        if not bid:
            self.notify("Selecione um livro para criar a anotação.")
            return
        self.open_note_editor(note_id=0, book_id=bid, book_title=ns.notes_book_title, note_text="")

    def load_notes(self, filter_book_id=None):
        """Carrega a lista de notas. Se filter_book_id for dado, filtra por livro."""
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

            # abrir detalhe ao tocar no item
            item.bind(on_release=partial(self.open_note_detail, note_id))

            # ícone editar
            item.add_widget(
                IconRightWidget(icon="pencil", on_release=partial(self.open_note_editor, note_id))
            )
            # ícone apagar
            item.add_widget(
                IconRightWidget(icon="delete", on_release=partial(self.delete_note_confirm, note_id))
            )

            lst.add_widget(item)


    # ---- Detalhar / Editar / Apagar ----

    def open_note_detail(self, note_id, *args):
        """Abre tela com a anotação completa."""
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
        """
        Abre o editor.
        - Se note_id > 0 -> carrega do DB
        - Se note_id == 0 -> usa (book_id, book_title) recebidos
        """
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

        # coloca o texto no campo
        editor.ids.editor_text.text = editor.note_text
        self.root.current = 'note_editor'

    def save_note_from_editor(self):
        """Salva criação/edição a partir da tela NoteEditor."""
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

        # Atualiza lists e abre detalhe
        self.load_notes()
        self.open_note_detail(note_id)

    def delete_note_confirm(self, note_id, *args):
        """Confirma exclusão e apaga a nota."""
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
            # Se estava no detalhe, volta para lista
            if self.root.current == 'note_detail':
                self.go_notes()
            else:
                self.load_notes()

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

        # ------------------ STATUS ------------------

    def status_db_to_ui(self, s: str) -> str:
        # DB → UI
        m = {"Concluído": "Lido", "Lendo": "Lendo", "Quero ler": "Quero ler"}
        return m.get((s or "").strip(), "Quero ler")

    def status_ui_to_db(self, s: str) -> str:
        # UI → DB
        m = {"Lido": "Concluído", "Lendo": "Lendo", "Quero ler": "Quero ler"}
        return m.get((s or "").strip(), "Quero ler")

    # Para usar no KV (comparações)
    def status_ui(self, status_db: str) -> str:
        return self.status_db_to_ui(status_db)
    
    def set_status_from_ui(self, ui_status: str):
        """Usuário escolheu 'Quero ler' | 'Lendo' | 'Lido' na UI."""
        detail = self.root.get_screen('detail_screen')
        if not detail.already_added:
            self.notify("Adicione o livro primeiro.")
            return

        s_db = self.status_ui_to_db(ui_status)
        pc = int(detail.page_count or 0)
        self.update_book_status(s_db, pc, detail) 

    def update_book_status(self, s_db, pc, detail):
        """
        s_db: 'Quero ler' | 'Lendo' | 'Concluído' (formato do DB)
        pc: total de páginas (int)
        detail: a tela BookDetailScreen atual
        """
        if s_db == "Concluído" and pc > 0:
            # marca como lido -> 100 %
            self.update_book_progress(pc)
            return
        if s_db == "Quero ler":
            # zera o progresso
            self.update_book_progress(0)
            return
        
        # "Lendo": só muda o status, mantém páginas
        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        try:
            cur.execute("UPDATE livros SET status = ? WHERE id = ?", (s_db, detail.book_id))
            conn.commit()
        except sqlite3.Error as e:
            print("Erro ao atualizar status:", e)
            self.notify("Não consegui salvar o status.")
        finally:
            conn.close()

        detail.book_status = s_db
        self._refresh_detail_progress()
        self.notify(f"Status atualizado para {self.status_db_to_ui(s_db)}.")

        # ------------------ PROGRESSO ------------------

    def _refresh_detail_progress(self):
        """Recalcula a % e ajusta status básico."""
        detail = self.root.get_screen('detail_screen')
        pc = int(detail.page_count or 0)
        pr = int(detail.pages_read or 0)
        if pc <= 0:
            detail.progress_percent = 0
            return
        pr = max(0, min(pr, pc))
        detail.pages_read = pr
        detail.progress_percent = int(round((pr / pc) * 100))

        # Regras simples de status (não força se usuário setou algo manualmente)
        if pr == 0:
            detail.book_status = 'Quero ler'
        elif pr >= pc:
            detail.book_status = 'Concluído'
        else:
            if detail.book_status not in ('Lendo', 'Concluído'):
                detail.book_status = 'Lendo'

    def prompt_update_progress(self):
        """Abre um diálogo para digitar as páginas lidas e salvar."""
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
        """Atualiza paginas/status no DB, grava progresso do dia (data local) e reflete na UI."""
        detail = self.root.get_screen('detail_screen')
        pc = int(detail.page_count or 0)
        old_pages = int(detail.pages_read or 0)
        new_pages = max(0, min(int(new_pages_read or 0), pc))

        # Status automático
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
            # Atualiza livro
            cur.execute(
                "UPDATE livros SET pagina_atual = ?, status = ? WHERE id = ?",
                (new_pages, status, detail.book_id)
            )

            # Log diário (apenas crescimento) — usando DATA LOCAL (sem UTC)
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

        # Reflete na UI e no gráfico
        detail.pages_read = new_pages
        detail.book_status = status
        self._refresh_detail_progress()
        self.render_reading_chart(days=7)  # mantém a tela de gráficos coerente
        self.notify("Progresso atualizado.")


        # Reflete na UI
        detail.pages_read = new_pages
        detail.book_status = status
        self._refresh_detail_progress()
        self.render_reading_chart(days=7)  # mantém a tela de gráficos coerente
        self.notify("Progresso atualizado.")

if __name__ == "__main__":
    RootsApp().run()
