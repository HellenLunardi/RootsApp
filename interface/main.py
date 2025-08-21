import sqlite3
import os.path
import re
import html
from datetime import date, timedelta

from kivy.clock import Clock
from kivy.network.urlrequest import UrlRequest
from urllib.parse import quote_plus

from kivymd.toast import toast
from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.boxlayout import MDBoxLayout

try:
    from kivy_garden.graph import Graph, MeshLinePlot
    HAS_GRAPH = True
except Exception:
    HAS_GRAPH = False

from kivymd.uix.menu import MDDropdownMenu


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


class RootsApp(MDApp):

    # ------------------ NAV ------------------

    def go_home(self):
        self.root.current = 'main_screen'

    def go_graph(self):
        self.root.current = 'graph_screen'
        # desenha/atualiza o gráfico quando entrar
        self.render_reading_chart(days=14)

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
        self.render_reading_chart(days=14)
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
        detail.book_id = book_id
        detail.book_title = title
        detail.authors = authors
        detail.cover_url = cover_url
        detail.page_count = page_count
        detail.description = description or ''
        detail.already_added = self.is_book_saved(book_id, title, authors)
        self.root.current = 'detail_screen'
        self.root.get_screen('main_screen').show_back = False

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
                raw_desc = volume_info.get('description', '') or ''
                description = self.clean_description(raw_desc)

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

    def render_reading_chart(self, days=14):
        gs = self.root.get_screen('graph_screen')
        box = gs.ids.chart_box
        box.clear_widgets()

        end = date.today()
        start = end - timedelta(days=days - 1)

        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date(data) AS d, SUM(COALESCE(paginas_lidas, 0)) AS pag
            FROM progresso_diario
            WHERE date(data) >= ?
            GROUP BY date(data)
            ORDER BY d
        """, (start.isoformat(),))
        rows = dict(cursor.fetchall())
        conn.close()

        xs, ys = [], []
        d = start
        i = 0
        while d <= end:
            xs.append(i)
            ys.append(int(rows.get(d.isoformat(), 0)))
            i += 1
            d += timedelta(days=1)

        if HAS_GRAPH:
            graph = Graph(
                xlabel='Dias', ylabel='Páginas',
                x_ticks_minor=0,
                x_ticks_major=max(1, days // 7),
                y_ticks_major=max(1, (max(ys) if ys else 1) // 5 or 1),
                x_grid=False, y_grid=True,
                xmin=0, xmax=max(0, len(xs) - 1),
                ymin=0, ymax=max(1, max(ys) if ys else 1),
                size_hint=(1, 1),
            )
            plot = MeshLinePlot()
            plot.points = list(zip(xs, ys))
            graph.add_plot(plot)
            box.add_widget(graph)
        else:
            from kivymd.uix.label import MDLabel
            total = sum(ys)
            avg = round(total / days, 1) if days else total
            box.add_widget(MDLabel(
                text=("Para ver o gráfico:\n"
                      "pip install kivy-garden\n"
                      "garden install graph\n\n"
                      f"Últimos {days} dias — Total: {total} | Média/dia: {avg}"),
                halign="center"
            ))

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

        items = [{
            "text": title,
            "on_release": (lambda b_id=bid, t=title: self._pick_book_for_note(b_id, t))
        } for bid, title in books] or [{
            "text": "Sem livros salvos",
            "on_release": lambda: self._pick_book_for_note("", "Sem livro")
        }]

        self._notes_menu = MDDropdownMenu(caller=btn, items=items, width_mult=4)
        self._notes_menu.open()

    def _pick_book_for_note(self, book_id, title):
        ns = self.root.get_screen('notes_screen')
        ns.notes_book_id = book_id or ""
        ns.notes_book_title = title if book_id else "Sem livros"
        if getattr(self, "_notes_menu", None):
            self._notes_menu.dismiss()

    def save_note_from_ui(self):
        ns = self.root.get_screen('notes_screen')
        txt = (ns.ids.note_input.text or "").strip()
        if not txt:
            self.notify("Escreva algo na anotação.")
            return

        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO anotacoes (livro_id, texto) VALUES (?, ?)",
                (ns.notes_book_id or None, txt)
            )
            conn.commit()
            ns.ids.note_input.text = ""
            self.notify("Anotação salva.")
            self.load_notes()
        except sqlite3.Error as e:
            print(f"Erro ao salvar anotação: {e}")
            self.notify("Erro ao salvar anotação.")
        finally:
            conn.close()

    def load_notes(self):
        ns = self.root.get_screen('notes_screen')
        lst = ns.ids.notes_list
        lst.clear_widgets()

        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.id, COALESCE(l.nome, 'Sem livro'), a.texto
            FROM anotacoes a
            LEFT JOIN livros l ON l.id = a.livro_id
            ORDER BY a.id DESC
        """)
        rows = cursor.fetchall()
        conn.close()

        from kivymd.uix.list import TwoLineListItem
        for _id, book_title, text in rows:
            lst.add_widget(TwoLineListItem(text=book_title, secondary_text=(text or "")[:120]))


if __name__ == "__main__":
    RootsApp().run()
