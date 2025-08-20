import requests
import sqlite3
import os.path

from kivymd.app import MDApp
from kivy.lang import Builder
from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty, NumericProperty

from kivymd.uix.boxlayout import MDBoxLayout
from kivy.uix.image import AsyncImage

class BookItem(MDBoxLayout):
    title = StringProperty('')
    cover_url = StringProperty('')
    book_id = StringProperty('')
    authors = StringProperty('')
    page_count = NumericProperty(0)

class MainScreen(Screen):
    pass

class RootsApp(MDApp):
    def build(self):
        # Chama a funçao para inicializar o banco de dados
        self.initialize_database()
        return Builder.load_file("roots.kv")
    
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
        """
        Busca livros na API e adiciona widgets na grade.
        Recebe o texto do campo de pesquisa como argumento.
        """
        api_url = f"https://www.googleapis.com/books/v1/volumes?q={query}"
        response = requests.get(api_url)

        books_grid = self.root.get_screen('main_screen').ids.books_grid
        books_grid.clear_widgets() # limpa a grade antes de adicionar o novo livro


        if response.status_code == 200:
            books_data = response.json().get('items', [])

            for item in books_data:
                volume_info = item.get('volumeInfo', {})

                # Coleta todas as informações necessárias do livro
                book_id = item.get('id', '')
                title = volume_info.get('title', 'Título Desconhecido')
                authors_list = volume_info.get('authors', ['Autor Desconhecido'])
                authors = ', '.join(authors_list)
                cover_url = volume_info.get('imageLinks', {}).get('thumbnail', '')
                page_count = volume_info.get('pageCount', 0)

                # Cria uma instancia do widget BookItem com as infos corretas
                book_widget = BookItem(
                    book_id=book_id,
                    title=title,
                    authors=authors,
                    cover_url=cover_url,
                    page_count=page_count
                )

                books_grid.add_widget(book_widget)
        else:
            print("Erro na busca da API")
        
    def save_book_to_database(self, book_id, title, authors, cover_url, page_count):
        """
        Salva um livro no banco de dados.
        """

        conn = sqlite3.connect('db/roots.db')
        cursor = conn.cursor()

        # Garante que a quantidade de paginas seja um inteiro
        try:
            page_count = int(page_count)
        except (ValueError, TypeError):
            page_count = 0 # Define um valor padrão se a conversão falhar

        try:
            # Note a correspondencia entre variaveis e as colunas do seu banco
            cursor.execute("""
                INSERT OR REPLACE INTO livros (
                    id, nome, autor, cover_url, qtde_paginas, status, pagina_atual, nota, genero_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (book_id, title, authors, cover_url, page_count, 'Quero ler', 0, 0, None))
            conn.commit()
            print(f"Livro '{title}' salvo com sucesso!")

            self.root.current = 'main_screen' # Retorna a tela inicial ao salvar um livro

        except sqlite3.Error as e:
            print(f"Erro ao salvar livro: {e}")
        finally:
            conn.close()
            

if __name__ == "__main__":
    RootsApp().run()