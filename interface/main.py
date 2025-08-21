import requests
import sqlite3
import os.path
import re
from kivy.network.urlrequest import UrlRequest
from urllib.parse import quote_plus
from kivymd.uix.snackbar import Snackbar
from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty, NumericProperty
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.uix.image import AsyncImage
from kivy.network.urlrequest import UrlRequest

class BookItem(ButtonBehavior, MDBoxLayout):
    title = StringProperty('')
    cover_url = StringProperty('')
    book_id = StringProperty('')
    authors = StringProperty('')
    page_count = NumericProperty(0)

class MainScreen(Screen):
    pass

class RootsApp(MDApp):
    @staticmethod
    def _normalize_text(s: str) -> str:
        s = (s or "").lower().strip()
        s = re.sub(r"[\s\-\_\.\,\:\;\!\?\(\)\[\]\{\}]+", " ", s)
        s = re.sub(r"\s+", " ", s)
        return s
    
    def build(self):
        # Chama a funçao para inicializar o banco de dados
        self.initialize_database()
        kv_path = os.path.join(os.path.dirname(__file__), "interface", "ui.kv")
        return Builder.load_file("ui.kv")
    
    def initialize_database(self):
        """
        Cria as tabelas de livros, generos, progresso_diario e anotacoes se elas não existirem.
        """
        if not os.path.exists("db"):
            os.makedirs("db")
        conn = sqlite3.connect("db/roots.db")
        cursor = conn.cursor()

        # Tabela de livros
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
                FOREIGN KEY (genero_id) REFERENCES generos(id)
            )
        """)

        # Tabela de gêneros
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo TEXT NOT NULL UNIQUE
            )
        """)

        # Tabela para o progresso de leitura diário
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS progresso_diario (
                livro_id TEXT,
                data TEXT,
                paginas_lidas INTEGER,
                FOREIGN KEY (livro_id) REFERENCES livros(id)
            )
        """)

        # Tabela de anotações
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
    


    def add_book_search(self, query):
        sm = self.root.get_screen('main_screen')
        books_grid = sm.ids.books_grid
        books_grid.clear_widgets() # limpa a grade antes de adicionar o novo livro

        q = (query or "").strip()
        if not q:
            Snackbar(text="Digite algo para buscar.").open()
        """
        Busca livros na API e adiciona widgets na grade.
        Recebe o texto do campo de pesquisa como argumento.
        """
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
            items = result.get('items', [])
            for item in items:
                volume_info = item.get('volumeInfo', {}) or {}
                # Coleta todas as informações necessárias do livro
                book_id = item.get('id', '')
                title = volume_info.get('title', 'Título Desconhecido') or ""
                authors_list = volume_info.get('authors', ['Autor Desconhecido'])
                authors = ', '.join(authors_list)
                cover_url = volume_info.get('imageLinks', {}).get('thumbnail', '') or ""
                page_count = volume_info.get('pageCount', 0) or 0

                # Cria uma instancia do widget BookItem com as infos correta

                if book_id and book_id in seen_ids:
                    continue

                ta_key = f"{self._normalize_text(title)}|{self._normalize_text(authors)}"
                if ta_key in seen_title_author:
                    continue

                if not cover_url: continue

                if book_id:
                    seen_ids.add(book_id)
                seen_title_author.add(ta_key)

                books_grid.add_widget(BookItem(
                    book_id=book_id,
                    title=title,
                    authors=authors,
                    cover_url=cover_url,
                    page_count=page_count
                ))

            if not books_grid.children:
                Snackbar(text="Nada encontrado.").open()

        def fail(req, err):
            print("Erro na busca:", err)
            Snackbar(text="Erro ao buscar livros, Verifique sua conexão.").open()

        UrlRequest(api_url, on_success=ok, on_error=fail, on_failure=fail, decode=True)

    def save_book_to_database(self, book_id, title, authors, cover_url, page_count):
        """
        Salva um livro no banco de dados.
        """
        db_path = os.path.join(self.user_data_dir, "db", "roots.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect('db/roots.db')
        cursor = conn.cursor()

        # Garante que a quantidade de paginas seja um inteiro
        try:
            page_count = int(page_count) if page_count is not None else 0
        except (ValueError, TypeError):
            page_count = 0 # Define um valor padrão se a conversão falhar

        try:
            # Note a correspondencia entre variaveis e as colunas do seu banco
            cursor.execute("""
                INSERT OR IGNORE INTO livros (
                    id, nome, autor, cover_url, qtde_paginas, status, pagina_atual, nota, genero_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (book_id, title, authors, cover_url, page_count, 'Quero ler', 0, 0, None))
            conn.commit()
            print(f"Livro '{title}' salvo com sucesso!")

            # Limpa a tela de resultados
            self.clear_books_grid()
            Snackbar(text=f"'{title}' adicionado à sua lista!", snackbar_x="10dp", snackbar_y="10dp", size_hint_x=.9).open()
            return True
        except sqlite3.Error as e:
            print(f"Erro ao salvar livro: {e}")
            return False
        finally:
            conn.close()

    def clear_books_grid(self):
        """
        Limpa a grade de livros na tela principal
        """
        books_grid = self.root.get_screen('main_screen').ids.books_grid
        books_grid.clear_widgets()            

if __name__ == "__main__":
    RootsApp().run()